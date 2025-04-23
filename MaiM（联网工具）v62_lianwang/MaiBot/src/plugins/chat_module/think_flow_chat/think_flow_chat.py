import time
from random import random
import traceback
from typing import List
from ...memory_system.Hippocampus import HippocampusManager
from ...moods.moods import MoodManager
from ...config.config import global_config
from ...chat.emoji_manager import emoji_manager
from .think_flow_generator import ResponseGenerator
from ...chat.message import MessageSending, MessageRecv, MessageThinking, MessageSet
from ...chat.message_sender import message_manager
from ...storage.storage import MessageStorage
from ...chat.utils import is_mentioned_bot_in_message, get_recent_group_detailed_plain_text
from ...chat.utils_image import image_path_to_base64
from ...willing.willing_manager import willing_manager
from ...message import UserInfo, Seg
from src.heart_flow.heartflow import heartflow
from src.common.logger import get_module_logger, CHAT_STYLE_CONFIG, LogConfig
from ...chat.chat_stream import chat_manager
from ...person_info.relationship_manager import relationship_manager
from ...chat.message_buffer import message_buffer
from src.plugins.respon_info_catcher.info_catcher import info_catcher_manager
from ...utils.timer_calculater import Timer
from src.do_tool.tool_use import ToolUser
import os
import re
import datetime

# 定义日志配置
chat_config = LogConfig(
    console_format=CHAT_STYLE_CONFIG["console_format"],
    file_format=CHAT_STYLE_CONFIG["file_format"],
)

logger = get_module_logger("think_flow_chat", config=chat_config)


class ThinkFlowChat:
    def __init__(self):
        self.storage = MessageStorage()
        self.gpt = ResponseGenerator()
        self.mood_manager = MoodManager.get_instance()
        self.mood_manager.start_mood_update()
        self.tool_user = ToolUser()
        # 不再直接初始化 web_searcher
        # from src.plugins.web_search import WebSearcher
        # self.web_searcher = WebSearcher()
        
        # 移除知识库维护初始化
        # self._setup_knowledge_maintenance()

    async def _create_thinking_message(self, message, chat, userinfo, messageinfo):
        """创建思考消息"""
        bot_user_info = UserInfo(
            user_id=global_config.BOT_QQ,
            user_nickname=global_config.BOT_NICKNAME,
            platform=messageinfo.platform,
        )

        thinking_time_point = round(time.time(), 2)
        thinking_id = "mt" + str(thinking_time_point)
        thinking_message = MessageThinking(
            message_id=thinking_id,
            chat_stream=chat,
            bot_user_info=bot_user_info,
            reply=message,
            thinking_start_time=thinking_time_point,
        )

        message_manager.add_message(thinking_message)

        return thinking_id

    async def _send_response_messages(self, message, chat, response_set: List[str], thinking_id) -> MessageSending:
        """发送回复消息"""
        container = message_manager.get_container(chat.stream_id)
        thinking_message = None

        for msg in container.messages:
            if isinstance(msg, MessageThinking) and msg.message_info.message_id == thinking_id:
                thinking_message = msg
                container.messages.remove(msg)
                break

        if not thinking_message:
            logger.warning("未找到对应的思考消息，可能已超时被移除")
            return None

        thinking_start_time = thinking_message.thinking_start_time
        message_set = MessageSet(chat, thinking_id)

        mark_head = False
        first_bot_msg = None
        for msg in response_set:
            message_segment = Seg(type="text", data=msg)
            bot_message = MessageSending(
                message_id=thinking_id,
                chat_stream=chat,
                bot_user_info=UserInfo(
                    user_id=global_config.BOT_QQ,
                    user_nickname=global_config.BOT_NICKNAME,
                    platform=message.message_info.platform,
                ),
                sender_info=message.message_info.user_info,
                message_segment=message_segment,
                reply=message,
                is_head=not mark_head,
                is_emoji=False,
                thinking_start_time=thinking_start_time,
            )
            if not mark_head:
                mark_head = True
                first_bot_msg = bot_message

            # print(f"thinking_start_time:{bot_message.thinking_start_time}")
            message_set.add_message(bot_message)
        message_manager.add_message(message_set)
        return first_bot_msg

    async def _handle_emoji(self, message, chat, response, send_emoji=""):
        """处理表情包"""
        if send_emoji:
            emoji_raw = await emoji_manager.get_emoji_for_text(send_emoji)
        else:
            emoji_raw = await emoji_manager.get_emoji_for_text(response)
        if emoji_raw:
            emoji_path, description = emoji_raw
            emoji_cq = image_path_to_base64(emoji_path)

            thinking_time_point = round(message.message_info.time, 2)

            message_segment = Seg(type="emoji", data=emoji_cq)
            bot_message = MessageSending(
                message_id="mt" + str(thinking_time_point),
                chat_stream=chat,
                bot_user_info=UserInfo(
                    user_id=global_config.BOT_QQ,
                    user_nickname=global_config.BOT_NICKNAME,
                    platform=message.message_info.platform,
                ),
                sender_info=message.message_info.user_info,
                message_segment=message_segment,
                reply=message,
                is_head=False,
                is_emoji=True,
            )

            message_manager.add_message(bot_message)

    async def _update_relationship(self, message: MessageRecv, response_set):
        """更新关系情绪"""
        ori_response = ",".join(response_set)
        stance, emotion = await self.gpt._get_emotion_tags(ori_response, message.processed_plain_text)
        await relationship_manager.calculate_update_relationship_value(
            chat_stream=message.chat_stream, label=emotion, stance=stance
        )
        self.mood_manager.update_mood_from_emotion(emotion, global_config.mood_intensity_factor)

    async def process_message(self, message_data: str) -> None:
        """处理消息并生成回复"""
        timing_results = {}
        response_set = None

        message = MessageRecv(message_data)
        groupinfo = message.message_info.group_info
        userinfo = message.message_info.user_info
        messageinfo = message.message_info

        # 消息加入缓冲池
        await message_buffer.start_caching_messages(message)

        # 创建聊天流
        chat = await chat_manager.get_or_create_stream(
            platform=messageinfo.platform,
            user_info=userinfo,
            group_info=groupinfo,
        )
        message.update_chat_stream(chat)

        # 创建心流与chat的观察
        heartflow.create_subheartflow(chat.stream_id)

        await message.process()
        logger.trace(f"消息处理成功{message.processed_plain_text}")

        # 过滤词/正则表达式过滤
        if self._check_ban_words(message.processed_plain_text, chat, userinfo) or self._check_ban_regex(
            message.raw_message, chat, userinfo
        ):
            return
        logger.trace(f"过滤词/正则表达式过滤成功{message.processed_plain_text}")

        await self.storage.store_message(message, chat)
        logger.trace(f"存储成功{message.processed_plain_text}")

        # 记忆激活
        with Timer("记忆激活", timing_results):
            interested_rate = await HippocampusManager.get_instance().get_activate_from_text(
                message.processed_plain_text, fast_retrieval=True
            )
        logger.trace(f"记忆激活: {interested_rate}")

        # 查询缓冲器结果，会整合前面跳过的消息，改变processed_plain_text
        buffer_result = await message_buffer.query_buffer_result(message)

        # 处理提及
        is_mentioned, reply_probability = is_mentioned_bot_in_message(message)

        # 意愿管理器：设置当前message信息
        willing_manager.setup(message, chat, is_mentioned, interested_rate)

        # 处理缓冲器结果
        if not buffer_result:
            await willing_manager.bombing_buffer_message_handle(message.message_info.message_id)
            willing_manager.delete(message.message_info.message_id)
            if message.message_segment.type == "text":
                logger.info(f"触发缓冲，已炸飞消息：{message.processed_plain_text}")
            elif message.message_segment.type == "image":
                logger.info("触发缓冲，已炸飞表情包/图片")
            elif message.message_segment.type == "seglist":
                logger.info("触发缓冲，已炸飞消息列")
            return

        # 获取回复概率
        is_willing = False
        if reply_probability != 1:
            is_willing = True
            reply_probability = await willing_manager.get_reply_probability(message.message_info.message_id)

            if message.message_info.additional_config:
                if "maimcore_reply_probability_gain" in message.message_info.additional_config.keys():
                    reply_probability += message.message_info.additional_config["maimcore_reply_probability_gain"]

        # 打印消息信息
        mes_name = chat.group_info.group_name if chat.group_info else "私聊"
        current_time = time.strftime("%H:%M:%S", time.localtime(message.message_info.time))
        willing_log = f"[回复意愿:{await willing_manager.get_willing(chat.stream_id):.2f}]" if is_willing else ""
        logger.info(
            f"[{current_time}][{mes_name}]"
            f"{chat.user_info.user_nickname}:"
            f"{message.processed_plain_text}{willing_log}[概率:{reply_probability * 100:.1f}%]"
        )

        do_reply = False
        if random() < reply_probability:
            try:
                do_reply = True

                # 回复前处理
                await willing_manager.before_generate_reply_handle(message.message_info.message_id)

                # 创建思考消息
                try:
                    with Timer("创建思考消息", timing_results):
                        thinking_id = await self._create_thinking_message(message, chat, userinfo, messageinfo)
                except Exception as e:
                    logger.error(f"心流创建思考消息失败: {e}")

                logger.trace(f"创建捕捉器，thinking_id:{thinking_id}")

                info_catcher = info_catcher_manager.get_info_catcher(thinking_id)
                info_catcher.catch_decide_to_response(message)

                # 观察
                try:
                    with Timer("观察", timing_results):
                        await heartflow.get_subheartflow(chat.stream_id).do_observe()
                except Exception as e:
                    logger.error(f"心流观察失败: {e}")
                    traceback.print_exc()

                info_catcher.catch_after_observe(timing_results["观察"])

                # 思考前使用工具
                update_relationship = ""
                get_mid_memory_id = []
                tool_result_info = {}
                send_emoji = ""
                try:
                    with Timer("思考前使用工具", timing_results):
                        tool_result = await self.tool_user.use_tool(
                            message.processed_plain_text,
                            message.message_info.user_info.user_nickname,
                            chat,
                            heartflow.get_subheartflow(chat.stream_id),
                        )
                        # 如果工具被使用且获得了结果，将收集到的信息合并到思考中
                        if tool_result.get("used_tools", False):
                            if "structured_info" in tool_result:
                                tool_result_info = tool_result["structured_info"]
                                get_mid_memory_id = []
                                update_relationship = ""

                                # 动态解析工具结果
                                for tool_name, tool_data in tool_result_info.items():
                                    if tool_name == "mid_chat_mem":
                                        for mid_memory in tool_data:
                                            get_mid_memory_id.append(mid_memory["content"])

                                    elif tool_name == "change_mood":
                                        for mood in tool_data:
                                            self.mood_manager.update_mood_from_emotion(
                                                mood["content"], global_config.mood_intensity_factor
                                            )

                                    elif tool_name == "change_relationship":
                                        update_relationship = tool_data[0]["content"]

                                    elif tool_name == "send_emoji":
                                        send_emoji = tool_data[0]["content"]

                except Exception as e:
                    logger.error(f"思考前工具调用失败: {e}")
                    logger.error(traceback.format_exc())

                # 处理关系更新
                if update_relationship:
                    stance, emotion = await self.gpt._get_emotion_tags_with_reason(
                        "你还没有回复", message.processed_plain_text, update_relationship
                    )
                    await relationship_manager.calculate_update_relationship_value(
                        chat_stream=message.chat_stream, label=emotion, stance=stance
                    )

                # 思考前脑内状态
                try:
                    with Timer("思考前脑内状态", timing_results):
                        current_mind, past_mind = await heartflow.get_subheartflow(
                            chat.stream_id
                        ).do_thinking_before_reply(
                            message_txt=message.processed_plain_text,
                            sender_name=message.message_info.user_info.user_nickname,
                            chat_stream=chat,
                            obs_id=get_mid_memory_id,
                            extra_info=tool_result_info,
                        )
                except Exception as e:
                    logger.error(f"心流思考前脑内状态失败: {e}")

                info_catcher.catch_afer_shf_step(timing_results["思考前脑内状态"], past_mind, current_mind)

                # 生成回复
                with Timer("生成回复", timing_results):
                    # 1. 先尝试使用统一搜索引擎获取信息
                    try:
                        from src.do_tool.tool_can_use import get_tool_instance
                        search_engine_tool = get_tool_instance("search_engine")
                        
                        if search_engine_tool:
                            # 执行智能搜索
                            search_result = await search_engine_tool.execute({
                                "query": message.processed_plain_text,
                                "chat_id": chat.stream_id,
                                "prioritize_recent": True,
                                "min_similarity": 0.4  # 设置较低的相似度阈值以增加召回率
                            })
                            
                            # 检查是否获得了搜索结果
                            if search_result and "content" in search_result and not search_result.get("skipped", False):
                                logger.info(f"智能搜索引擎获取到结果，来源: {search_result.get('source', '未知')}")
                                
                                # 使用搜索结果生成增强回复
                                search_content = search_result["content"]
                                
                                # 判断是否需要单独生成LLM回复
                                has_original_response = bool(response_set)
                                if not has_original_response:
                                    # 还没有生成原始回复，先用模型生成一个基本回复
                                    response_set = await self.gpt.generate_response(message, thinking_id)
                                
                                # 判断搜索结果相关性
                                search_relevance = "高"  # 默认认为相关性高
                                
                                # 检查搜索结果是否足够有价值
                                search_has_value = True
                                if len(search_content.strip()) < 50 or "未找到相关信息" in search_content:
                                    # 如果知识库查询被禁用，则降低判断标准，认为网络搜索结果更有价值
                                    knowledge_base_enable = getattr(global_config, "knowledge_base_enable", True)
                                    
                                    if not knowledge_base_enable and search_result.get("web_search_used", False):
                                        # 知识库禁用且有网络搜索结果，则认为结果有价值
                                        search_has_value = True
                                        logger.info("知识库查询已禁用，网络搜索结果被视为有价值")
                                    else:
                                        search_has_value = False
                                        logger.info("搜索结果价值不高，减少权重")
                                
                                # 如果有网络搜索结果，准备融合
                                if search_result.get("web_search_used", False):
                                    search_prompt = f"""你现在扮演{global_config.BOT_NICKNAME}，一个{global_config.personality_core}的角色。你有自己的知识、想法和个性，同时刚获得了一些新信息。

你的原始想法：{response_set}

你刚获得的信息：
{search_content}

搜索信息相关性：{search_relevance}
是否为时间敏感信息：{"是" if "time_sensitive" in search_result.get("tags", []) else "否"}

请融合这些信息，生成一个新的回复：
1. 保持你的个性和说话风格，表现出{global_config.personality_core}的特点
2. 巧妙地将新信息融入你的回复中，就像是你本来就知道的一样
3. 避免机械地重复信息，用自然的方式表达
4. 控制在4-5句话内，总长不超过200字
5. 如果新信息与你的专长或兴趣（比如游戏、技术）相关，可以加入你的个人见解
6. 完全避免使用括号和特殊标记
7. 使用日常对话口吻，像在和朋友聊天
8. 如果信息是时间敏感的，可以自然地表明，如"刚看到""最近"等

回复："""
                                else:
                                    # 只有知识库结果
                                    search_prompt = f"""你现在扮演{global_config.BOT_NICKNAME}，一个{global_config.personality_core}的角色。你有自己的知识、想法和个性，同时刚获得了一些参考信息。

你的原始想法：{response_set}

参考信息：
{search_content}

搜索信息相关性：{search_relevance}
是否为时间敏感信息：{"是" if "time_sensitive" in search_result.get("tags", []) else "否"}

请根据这些信息，生成一个新的回复：
1. 保持你的个性和说话风格，表现出{global_config.personality_core}的特点
2. 如果参考信息有价值，自然地融入回复中，就像是你本来就知道的一样
3. 如果参考信息与你的专长或兴趣相关，可以加入你的个人见解
4. 如果参考信息不相关，可以忽略，保持你的原始回复
5. 使用日常对话口吻，像在和朋友聊天
6. 控制在4-5句话内，总长不超过200字
7. 完全避免使用括号和特殊标记
8. 如果信息是时间敏感的，可以自然地表明，如"刚看到""最近"等

回复："""
                                
                                # 生成融合后的回复
                                try:
                                    # 记录搜索结果的详细信息
                                    logger.info(f"搜索结果详情 - 来源: {search_result.get('source', '未知')}, "
                                              f"长度: {len(search_content)}, "
                                              f"网络搜索使用: {search_result.get('web_search_used', False)}, "
                                              f"判定价值: {search_has_value}")
                                    
                                    # 只有当搜索结果有价值时才进行融合
                                    if search_has_value:
                                        logger.info(f"尝试融合搜索结果到回复中")
                                        enhanced_response = await self.gpt.model_normal.generate_response(search_prompt)
                                        if enhanced_response:
                                            # 处理回复，拆分为自然的句子
                                            sentences = re.split(r'(?<=[。！？!?])|(?<=\.(?![0-9]))', enhanced_response[0])
                                            # 过滤空句子并最多取3句
                                            filtered_sentences = [s.strip() for s in sentences if s.strip()][:3]
                                            
                                            # 如果首句很短并且有多句，适当合并
                                            if len(filtered_sentences) > 1 and len(filtered_sentences[0]) < 20:
                                                filtered_sentences[0] += filtered_sentences.pop(1)
                                            
                                            # 检查最后一句是否完整
                                            if filtered_sentences and len(filtered_sentences[-1]) < 15 and any(w in filtered_sentences[-1] for w in ["不过", "然而", "但是"]):
                                                # 可能是不完整句子，尝试保留原始文本
                                                filtered_sentences[-1] = enhanced_response[0][enhanced_response[0].rfind(filtered_sentences[-1][:-1]):]
                                            
                                            logger.info(f"融合前的回复: {response_set}")
                                            # 替换原始回复
                                            response_set = filtered_sentences
                                            logger.info(f"融合后的回复: {response_set}")
                                            logger.info("已将搜索结果融入回复")
                                        else:
                                            logger.warning("融合响应生成失败，保持原始回复")
                                    else:
                                        logger.info("搜索结果价值低，保持原始回复")
                                except Exception as e:
                                    logger.error(f"融合搜索结果失败: {e}")
                                    # 如果融合失败，继续使用原始回复
                    except Exception as e:
                        logger.error(f"使用智能搜索引擎失败: {str(e)}")
                        traceback.print_exc()
                        # 如果智能搜索失败，继续常规流程
                        if not response_set:
                            response_set = await self.gpt.generate_response(message, thinking_id)
                    
                    # 如果没有找到相关知识，使用原有方式生成回复
                    if not response_set:
                        response_set = await self.gpt.generate_response(message, thinking_id)

                # 检查是否需要搜索
                try:
                    # 使用智能搜索引擎工具已经在前面执行过了，这里不再需要额外的搜索逻辑
                    pass
                except Exception as e:
                    logger.error(f"搜索决策或执行失败: {str(e)}")

                info_catcher.catch_after_generate_response(timing_results["生成回复"])

                if not response_set:
                    logger.info("回复生成失败，返回为空")
                    return

                # 发送消息
                try:
                    with Timer("发送消息", timing_results):
                        first_bot_msg = await self._send_response_messages(message, chat, response_set, thinking_id)
                except Exception as e:
                    logger.error(f"心流发送消息失败: {e}")

                info_catcher.catch_after_response(timing_results["发送消息"], response_set, first_bot_msg)

                info_catcher.done_catch()

                # 处理表情包
                try:
                    with Timer("处理表情包", timing_results):
                        if global_config.emoji_chance == 1:
                            if send_emoji:
                                logger.info(f"麦麦决定发送表情包{send_emoji}")
                                await self._handle_emoji(message, chat, response_set, send_emoji)
                        else:
                            if random() < global_config.emoji_chance:
                                await self._handle_emoji(message, chat, response_set)
                except Exception as e:
                    logger.error(f"心流处理表情包失败: {e}")

                try:
                    with Timer("思考后脑内状态更新", timing_results):
                        stream_id = message.chat_stream.stream_id
                        chat_talking_prompt = ""
                        if stream_id:
                            chat_talking_prompt = get_recent_group_detailed_plain_text(
                                stream_id, limit=global_config.MAX_CONTEXT_SIZE, combine=True
                            )

                        await heartflow.get_subheartflow(stream_id).do_thinking_after_reply(
                            response_set, chat_talking_prompt, tool_result_info
                        )
                except Exception as e:
                    logger.error(f"心流思考后脑内状态更新失败: {e}")

                # 回复后处理
                await willing_manager.after_generate_reply_handle(message.message_info.message_id)

            except Exception as e:
                logger.error(f"心流处理消息失败: {e}")
                logger.error(traceback.format_exc())

        # 输出性能计时结果
        if do_reply:
            timing_str = " | ".join([f"{step}: {duration:.2f}秒" for step, duration in timing_results.items()])
            trigger_msg = message.processed_plain_text
            response_msg = " ".join(response_set) if response_set else "无回复"
            logger.info(f"触发消息: {trigger_msg[:20]}... | 思维消息: {response_msg[:20]}... | 性能计时: {timing_str}")
        else:
            # 不回复处理
            await willing_manager.not_reply_handle(message.message_info.message_id)

        # 意愿管理器：注销当前message信息
        willing_manager.delete(message.message_info.message_id)

    def _check_ban_words(self, text: str, chat, userinfo) -> bool:
        """检查消息中是否包含过滤词"""
        for word in global_config.ban_words:
            if word in text:
                logger.info(
                    f"[{chat.group_info.group_name if chat.group_info else '私聊'}]{userinfo.user_nickname}:{text}"
                )
                logger.info(f"[过滤词识别]消息中含有{word}，filtered")
                return True
        return False

    def _check_ban_regex(self, text: str, chat, userinfo) -> bool:
        """检查消息是否匹配过滤正则表达式"""
        for pattern in global_config.ban_msgs_regex:
            if pattern.search(text):
                logger.info(
                    f"[{chat.group_info.group_name if chat.group_info else '私聊'}]{userinfo.user_nickname}:{text}"
                )
                logger.info(f"[正则表达式过滤]消息匹配到{pattern}，filtered")
                return True
        return False
