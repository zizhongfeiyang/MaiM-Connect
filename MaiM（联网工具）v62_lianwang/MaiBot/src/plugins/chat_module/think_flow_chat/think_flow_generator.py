from typing import List, Optional, Dict, Any
import random
import time
import traceback

from ...models.utils_model import LLM_request
from ...config.config import global_config
from ...chat.message import MessageRecv
from .think_flow_prompt_builder import prompt_builder
from ...chat.utils import process_llm_response
from src.common.logger import get_module_logger, LogConfig, LLM_STYLE_CONFIG
from src.plugins.respon_info_catcher.info_catcher import info_catcher_manager
from ...utils.timer_calculater import Timer

from src.plugins.moods.moods import MoodManager

# 定义日志配置
llm_config = LogConfig(
    # 使用消息发送专用样式
    console_format=LLM_STYLE_CONFIG["console_format"],
    file_format=LLM_STYLE_CONFIG["file_format"],
)

logger = get_module_logger("llm_generator", config=llm_config)


class ResponseGenerator:
    def __init__(self):
        self.model_normal = LLM_request(
            model=global_config.llm_normal,
            temperature=global_config.llm_normal["temp"],
            max_tokens=256,
            request_type="response_heartflow",
        )

        self.model_sum = LLM_request(
            model=global_config.llm_summary_by_topic, temperature=0.6, max_tokens=2000, request_type="relation"
        )
        self.current_model_type = "r1"  # 默认使用 R1
        self.current_model_name = "unknown model"
        # 初始化 tool_user
        from src.do_tool.tool_use import ToolUser
        self.tool_user = ToolUser()

    async def generate_response(self, message: MessageRecv, thinking_id: str) -> Optional[List[str]]:
        """根据当前模型类型选择对应的生成函数"""

        logger.info(
            f"思考:{message.processed_plain_text[:30] + '...' if len(message.processed_plain_text) > 30 else message.processed_plain_text}"
        )

        arousal_multiplier = MoodManager.get_instance().get_arousal_multiplier()

        with Timer() as t_generate_response:
            checked = False
            if random.random() > 0:
                checked = False
                current_model = self.model_normal
                current_model.temperature = (
                    global_config.llm_normal["temp"] * arousal_multiplier
                )  # 激活度越高，温度越高
                model_response = await self._generate_response_with_model(
                    message, current_model, thinking_id, mode="normal"
                )

                model_checked_response = model_response
            else:
                checked = True
                current_model = self.model_normal
                current_model.temperature = (
                    global_config.llm_normal["temp"] * arousal_multiplier
                )  # 激活度越高，温度越高
                print(f"生成{message.processed_plain_text}回复温度是：{current_model.temperature}")
                model_response = await self._generate_response_with_model(
                    message, current_model, thinking_id, mode="simple"
                )

                current_model.temperature = global_config.llm_normal["temp"]
                model_checked_response = await self._check_response_with_model(
                    message, model_response, current_model, thinking_id
                )

        if model_response:
            if checked:
                logger.info(
                    f"{global_config.BOT_NICKNAME}的回复是：{model_response}，思忖后，回复是：{model_checked_response},生成回复时间: {t_generate_response.human_readable}"
                )
            else:
                logger.info(
                    f"{global_config.BOT_NICKNAME}的回复是：{model_response},生成回复时间: {t_generate_response.human_readable}"
                )

            model_processed_response = await self._process_response(model_checked_response)

            return model_processed_response
        else:
            logger.info(f"{self.current_model_type}思考，失败")
            return None

    async def _generate_response_with_model(
        self, message: MessageRecv, model: LLM_request, thinking_id: str, mode: str = "normal"
    ) -> str:
        sender_name = ""

        info_catcher = info_catcher_manager.get_info_catcher(thinking_id)

        if message.chat_stream.user_info.user_cardname and message.chat_stream.user_info.user_nickname:
            sender_name = (
                f"[({message.chat_stream.user_info.user_id}){message.chat_stream.user_info.user_nickname}]"
                f"{message.chat_stream.user_info.user_cardname}"
            )
        elif message.chat_stream.user_info.user_nickname:
            sender_name = f"({message.chat_stream.user_info.user_id}){message.chat_stream.user_info.user_nickname}"
        else:
            sender_name = f"用户({message.chat_stream.user_info.user_id})"

        # 构建prompt
        with Timer() as t_build_prompt:
            if mode == "normal":
                prompt = await prompt_builder._build_prompt(
                    message.chat_stream,
                    message_txt=message.processed_plain_text,
                    sender_name=sender_name,
                    stream_id=message.chat_stream.stream_id,
                )
            elif mode == "simple":
                prompt = await prompt_builder._build_prompt_simple(
                    message.chat_stream,
                    message_txt=message.processed_plain_text,
                    sender_name=sender_name,
                    stream_id=message.chat_stream.stream_id,
                )
        logger.info(f"构建{mode}prompt时间: {t_build_prompt.human_readable}")

        try:
            content, reasoning_content, self.current_model_name = await model.generate_response(prompt)

            info_catcher.catch_after_llm_generated(
                prompt=prompt, response=content, reasoning_content=reasoning_content, model_name=self.current_model_name
            )

        except Exception:
            logger.exception("生成回复时出错")
            return None

        return content

    async def _check_response_with_model(
        self, message: MessageRecv, content: str, model: LLM_request, thinking_id: str
    ) -> str:
        _info_catcher = info_catcher_manager.get_info_catcher(thinking_id)

        sender_name = ""
        if message.chat_stream.user_info.user_cardname and message.chat_stream.user_info.user_nickname:
            sender_name = (
                f"[({message.chat_stream.user_info.user_id}){message.chat_stream.user_info.user_nickname}]"
                f"{message.chat_stream.user_info.user_cardname}"
            )
        elif message.chat_stream.user_info.user_nickname:
            sender_name = f"({message.chat_stream.user_info.user_id}){message.chat_stream.user_info.user_nickname}"
        else:
            sender_name = f"用户({message.chat_stream.user_info.user_id})"

        # 构建prompt
        with Timer() as t_build_prompt_check:
            prompt = await prompt_builder._build_prompt_check_response(
                message.chat_stream,
                message_txt=message.processed_plain_text,
                sender_name=sender_name,
                stream_id=message.chat_stream.stream_id,
                content=content,
            )
        logger.info(f"构建check_prompt: {prompt}")
        logger.info(f"构建check_prompt时间: {t_build_prompt_check.human_readable}")

        try:
            checked_content, reasoning_content, self.current_model_name = await model.generate_response(prompt)

            # info_catcher.catch_after_llm_generated(
            #     prompt=prompt,
            #     response=content,
            #     reasoning_content=reasoning_content,
            #     model_name=self.current_model_name)

        except Exception:
            logger.exception("检查回复时出错")
            return None

        return checked_content

    async def _get_emotion_tags(self, content: str, processed_plain_text: str):
        """提取情感标签，结合立场和情绪"""
        try:
            # 构建提示词，结合回复内容、被回复的内容以及立场分析
            prompt = f"""
            请严格根据以下对话内容，完成以下任务：
            1. 判断回复者对被回复者观点的直接立场：
            - "支持"：明确同意或强化被回复者观点
            - "反对"：明确反驳或否定被回复者观点
            - "中立"：不表达明确立场或无关回应
            2. 从"开心,愤怒,悲伤,惊讶,平静,害羞,恐惧,厌恶,困惑"中选出最匹配的1个情感标签
            3. 按照"立场-情绪"的格式直接输出结果，例如："反对-愤怒"
            4. 考虑回复者的人格设定为{global_config.personality_core}

            对话示例：
            被回复：「A就是笨」
            回复：「A明明很聪明」 → 反对-愤怒

            当前对话：
            被回复：「{processed_plain_text}」
            回复：「{content}」

            输出要求：
            - 只需输出"立场-情绪"结果，不要解释
            - 严格基于文字直接表达的对立关系判断
            """

            # 调用模型生成结果
            result, _, _ = await self.model_sum.generate_response(prompt)
            result = result.strip()

            # 解析模型输出的结果
            if "-" in result:
                stance, emotion = result.split("-", 1)
                valid_stances = ["支持", "反对", "中立"]
                valid_emotions = ["开心", "愤怒", "悲伤", "惊讶", "害羞", "平静", "恐惧", "厌恶", "困惑"]
                if stance in valid_stances and emotion in valid_emotions:
                    return stance, emotion  # 返回有效的立场-情绪组合
                else:
                    logger.debug(f"无效立场-情感组合:{result}")
                    return "中立", "平静"  # 默认返回中立-平静
            else:
                logger.debug(f"立场-情感格式错误:{result}")
                return "中立", "平静"  # 格式错误时返回默认值

        except Exception as e:
            logger.debug(f"获取情感标签时出错: {e}")
            return "中立", "平静"  # 出错时返回默认值

    async def _get_emotion_tags_with_reason(self, content: str, processed_plain_text: str, reason: str):
        """提取情感标签，结合立场和情绪"""
        try:
            # 构建提示词，结合回复内容、被回复的内容以及立场分析
            prompt = f"""
            请严格根据以下对话内容，完成以下任务：
            1. 判断回复者对被回复者观点的直接立场：
            - "支持"：明确同意或强化被回复者观点
            - "反对"：明确反驳或否定被回复者观点
            - "中立"：不表达明确立场或无关回应
            2. 从"开心,愤怒,悲伤,惊讶,平静,害羞,恐惧,厌恶,困惑"中选出最匹配的1个情感标签
            3. 按照"立场-情绪"的格式直接输出结果，例如："反对-愤怒"
            4. 考虑回复者的人格设定为{global_config.personality_core}

            对话示例：
            被回复：「A就是笨」
            回复：「A明明很聪明」 → 反对-愤怒

            当前对话：
            被回复：「{processed_plain_text}」
            回复：「{content}」
            
            原因：「{reason}」

            输出要求：
            - 只需输出"立场-情绪"结果，不要解释
            - 严格基于文字直接表达的对立关系判断
            """

            # 调用模型生成结果
            result, _, _ = await self.model_sum.generate_response(prompt)
            result = result.strip()

            # 解析模型输出的结果
            if "-" in result:
                stance, emotion = result.split("-", 1)
                valid_stances = ["支持", "反对", "中立"]
                valid_emotions = ["开心", "愤怒", "悲伤", "惊讶", "害羞", "平静", "恐惧", "厌恶", "困惑"]
                if stance in valid_stances and emotion in valid_emotions:
                    return stance, emotion  # 返回有效的立场-情绪组合
                else:
                    logger.debug(f"无效立场-情感组合:{result}")
                    return "中立", "平静"  # 默认返回中立-平静
            else:
                logger.debug(f"立场-情感格式错误:{result}")
                return "中立", "平静"  # 格式错误时返回默认值

        except Exception as e:
            logger.debug(f"获取情感标签时出错: {e}")
            return "中立", "平静"  # 出错时返回默认值

    async def _process_response(self, content: str) -> List[str]:
        """处理响应内容，返回处理后的内容和情感标签"""
        if not content:
            return None

        processed_response = process_llm_response(content)

        # print(f"得到了处理后的llm返回{processed_response}")

        return processed_response

    async def summarize_search_results(self, query: str, search_results: str, chat_stream=None) -> str:
        """
        总结搜索结果并存入本地数据库
        :param query: 原始查询
        :param search_results: 格式化后的搜索结果
        :param chat_stream: 聊天流对象
        :return: 总结后的文本
        """
        prompt = f"""作为{global_config.BOT_NICKNAME}，请用你独特的方式总结以下信息。记住，你是{global_config.personality_core}的性格。

用户问题：{query}

搜索结果：
{search_results}

请以你的视角总结这些信息：
1. 提取最核心、最有价值的事实和数据
2. 如果涉及时间敏感信息，确保明确指出时效性
3. 如果有多个来源的冲突信息，指出不同观点
4. 保留任何可能对用户有帮助的专业术语或关键词
5. 如果内容涉及你感兴趣的领域(如游戏、技术)，可以加入你的专业见解

总结要求：
1. 以{global_config.BOT_NICKNAME}的身份写作，展现你的性格特点
2. 内容简洁精炼，控制在200字以内
3. 使用自然的对话语言，避免过于正式或学术化的表达
4. 如果信息不足或质量低，诚实地表明局限性
5. 完全避免使用括号或特殊标记来表达情感或态度

直接输出总结内容："""
        
        try:
            # 生成总结
            response = await self.model_normal.generate_response(prompt)
            summary = response[0] if response else ""

            # 将总结存入本地数据库
            try:
                # 直接使用StoreKnowledgeTool的execute方法
                from src.do_tool.tool_can_use import get_tool_instance
                store_knowledge_tool = get_tool_instance("store_knowledge")
                
                # 提取可能的时间信息
                import re
                time_info = re.search(r"(最近|前不久|不久前|今天|昨天|本周|上周|本月|今年|去年|(\d{4}年|\d{1,2}月|\d{1,2}日))", summary)
                
                # 设置重要性 - 根据时效性和关键词设置在1-5的范围内
                # 默认重要程度为中等(3)
                importance = 3
                if time_info:
                    # 有明确时间信息的内容重要性略高(4)
                    importance = 4
                
                # 检查关键词提高重要性
                importance_keywords = ["最新", "重要", "关键", "紧急", "重大", "突发", "更新", "发布", "宣布"]
                if any(word in query.lower() or word in summary.lower() for word in importance_keywords):
                    importance = 5  # 最高重要性
                
                # 添加相关标签
                tags = ["search_result", "ai_summary"]
                if any(word in query.lower() or word in summary.lower() for word in ["最新", "最近", "今日", "本周"]):
                    tags.append("time_sensitive")
                
                # 从内容中提取关键词作为标签
                try:
                    # 预定义的停用词列表
                    stopwords = ["的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这", "什么", "没", "这个", "可以", "但", "这些", "那", "大", "来", "这样", "因为", "里", "让", "她", "他", "它", "做", "被", "所以", "还", "能", "给", "我们", "你们", "他们", "她们", "因此", "如此", "如何"]
                    
                    # 合并查询和摘要文本
                    full_text = query + " " + summary
                    
                    # 分词，可以使用结巴或直接按空格分词
                    import jieba
                    words = jieba.cut(full_text)
                    
                    # 统计词频，过滤停用词和短词
                    word_freq = {}
                    for word in words:
                        word = word.strip().lower()
                        if word and len(word) > 1 and word not in stopwords:
                            word_freq[word] = word_freq.get(word, 0) + 1
                    
                    # 按频率排序并取前5个作为标签
                    keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
                    
                    # 添加到标签中
                    for keyword, _ in keywords:
                        if keyword not in tags and len(keyword) > 1:
                            tags.append(keyword)
                    
                    logger.info(f"提取的关键词标签: {tags}")
                
                except Exception as e:
                    logger.error(f"提取关键词标签失败: {e}")
                    # 失败时使用一些基础标签，确保功能正常
                    if "游戏" in query or "游戏" in summary:
                        tags.append("游戏")
                    if "新闻" in query or "新闻" in summary:
                        tags.append("新闻")
                
                # 构建存储参数
                store_params = {
                    "query": query,
                    "content": summary,
                    "source": "web_search",
                    "timestamp": time.time(),
                    "tags": tags,
                    "importance": importance,
                    "ttl": (7 + importance) * 24 * 60 * 60  # 根据重要性调整保存时间，最长12天
                }
                
                # 执行知识存储
                knowledge_result = await store_knowledge_tool.execute(store_params)
                logger.info(f"搜索结果已存入本地数据库: {knowledge_result}")
            except Exception as e:
                logger.error(f"存储搜索结果失败: {e}")
                import traceback
                traceback.print_exc()

            return summary
            
        except Exception as e:
            logger.error(f"总结搜索结果失败: {e}")
            return "抱歉，我无法处理搜索结果。请稍后再试。"

    async def correct_response_with_search(self, query: str, original_response: str, search_results: str, chat_stream=None) -> str:
        """
        根据搜索结果修正原始回复，并将知识存入数据库
        :param query: 原始查询
        :param original_response: 原始回复
        :param search_results: 格式化后的搜索结果
        :param chat_stream: 聊天流对象
        :return: 修正后的回复
        """
        # 先总结搜索结果并存入数据库
        summary = await self.summarize_search_results(query, search_results, chat_stream)
        
        # 然后基于数据库内容生成自然流畅的回复
        prompt = f"""你之前给出了一个不确定的回答，现在有了新的知识。请根据这些知识生成一个自然流畅的回复。

用户问题：{query}

你之前的回答：{original_response}

新获取的知识：
{summary}

请生成一个自然流畅的回复，要求：
1. 不要直接引用或列举知识内容
2. 用对话的方式表达，就像在和朋友聊天
3. 如果知识证实了你的回答，可以保持原回答并自然地补充细节
4. 如果知识与你的回答有冲突，请自然地修正为正确的信息
5. 如果知识提供了新的相关信息，请自然地整合到回答中
6. 如果知识与问题无关，请自然地说明没有找到相关信息

回复："""
        
        try:
            response = await self.model_normal.generate_response(prompt)
            return response[0] if response else original_response
        except Exception as e:
            logger.error(f"生成回复失败: {e}")
            return original_response
