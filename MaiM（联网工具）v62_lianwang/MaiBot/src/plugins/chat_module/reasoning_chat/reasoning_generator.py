from typing import List, Optional, Tuple, Union
import random
import re
import time
import traceback

from ...models.utils_model import LLM_request
from ...config.config import global_config
from ...chat.message import MessageThinking, MessageRecv
from .reasoning_prompt_builder import prompt_builder
from ...chat.utils import process_llm_response
from ...utils.timer_calculater import Timer
from src.common.logger import get_module_logger, LogConfig, LLM_STYLE_CONFIG
from src.plugins.respon_info_catcher.info_catcher import info_catcher_manager

# 定义日志配置
llm_config = LogConfig(
    # 使用消息发送专用样式
    console_format=LLM_STYLE_CONFIG["console_format"],
    file_format=LLM_STYLE_CONFIG["file_format"],
)

logger = get_module_logger("llm_generator", config=llm_config)


class ResponseGenerator:
    def __init__(self):
        self.model_reasoning = LLM_request(
            model=global_config.llm_reasoning,
            temperature=0.7,
            max_tokens=3000,
            request_type="response_reasoning",
        )
        self.model_normal = LLM_request(
            model=global_config.llm_normal,
            temperature=global_config.llm_normal["temp"],
            max_tokens=256,
            request_type="response_reasoning",
        )

        self.model_sum = LLM_request(
            model=global_config.llm_summary_by_topic, temperature=0.7, max_tokens=3000, request_type="relation"
        )
        self.current_model_type = "r1"  # 默认使用 R1
        self.current_model_name = "unknown model"

    async def generate_response(self, message: MessageRecv, thinking_id: str) -> List[str]:
        """生成回复

        Args:
            message: 用户的消息
            thinking_id: 思考消息的ID

        Returns:
            List[str]: 回复列表
        """
        reasoning_cache = None
        api_reasoning_content = None

        try:
            with Timer("构建推理提示词") as timer:
                prompt, mode = await self.prompt_builder.build_prompt(message)
                logger.debug(f"构建提示词用时: {timer.elapsed_time:.2f}秒")

            llm_reasoning_params = {
                "temperature": 0.7,
                "request_type": "reasoning",
            }

            model = global_config.llm_reasoning

            if global_config.llm_reasoning["name"].startswith("Pro"):
                llm_reasoning_params["temperature"] = model.get("temp", 0.7)

                probability = random()
                if probability < global_config.MODEL_R1_PROBABILITY:
                    # 使用R1模型
                    model["name"] = "Pro/deepseek-ai/deepseek-chat"
                    logger.info("推理使用R1模型")
                elif probability < global_config.MODEL_R1_PROBABILITY + global_config.MODEL_V3_PROBABILITY:
                    # 使用V3模型
                    model["name"] = "Pro/qwen/qwen-max"
                    logger.info("推理使用V3模型")
                else:
                    # 使用蒸馏模型
                    model["name"] = "deepseek-ai/deepseek-chat"
                    logger.info("推理使用精华蒸馏模型")

            llm = LLM_request(model=model, **llm_reasoning_params)

            conversation_reasoning_start = time.time()
            api_response, api_reasoning_content, model_name, *additional = await llm.generate_response(prompt)
            reasoning_cache = {
                "reasoning_content": api_reasoning_content,
                "api_response": api_response,
                "additional": additional,
            }

            # 清理模型输出中的括号注释内容
            api_response = await self._process_response(api_response, api_reasoning_content)

            conversation_reasoning_end = time.time()
            time_cost = conversation_reasoning_end - conversation_reasoning_start
            logger.info(f"信息处理时间: {time_cost:.2f}秒")

            # 处理聊天格式
            processed_responses = self._format_response(api_response)

            return processed_responses
        except Exception as e:
            logger.error(f"推理生成回复失败: {e}")
            logger.error(f"失败原因: {traceback.format_exc()}")
            logger.error(f"推理缓存: {reasoning_cache}")
            error_response = ["抱歉，我现在无法正确理解你的消息。"]
            return error_response

    async def _generate_response_with_model(self, message: MessageThinking, model: LLM_request, thinking_id: str):
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

        logger.debug("开始使用生成回复-2")
        # 构建prompt
        with Timer() as t_build_prompt:
            prompt = await prompt_builder._build_prompt(
                message.chat_stream,
                message_txt=message.processed_plain_text,
                sender_name=sender_name,
                stream_id=message.chat_stream.stream_id,
            )
        logger.info(f"构建prompt时间: {t_build_prompt.human_readable}")

        try:
            content, reasoning_content, self.current_model_name = await model.generate_response(prompt)

            info_catcher.catch_after_llm_generated(
                prompt=prompt, response=content, reasoning_content=reasoning_content, model_name=self.current_model_name
            )

        except Exception:
            logger.exception("生成回复时出错")
            return None

        # 保存到数据库
        # self._save_to_db(
        #     message=message,
        #     sender_name=sender_name,
        #     prompt=prompt,
        #     content=content,
        #     reasoning_content=reasoning_content,
        #     # reasoning_content_check=reasoning_content_check if global_config.enable_kuuki_read else ""
        # )

        return content

    # def _save_to_db(
    #     self,
    #     message: MessageRecv,
    #     sender_name: str,
    #     prompt: str,
    #     content: str,
    #     reasoning_content: str,
    # ):
    #     """保存对话记录到数据库"""
    #     db.reasoning_logs.insert_one(
    #         {
    #             "time": time.time(),
    #             "chat_id": message.chat_stream.stream_id,
    #             "user": sender_name,
    #             "message": message.processed_plain_text,
    #             "model": self.current_model_name,
    #             "reasoning": reasoning_content,
    #             "response": content,
    #             "prompt": prompt,
    #         }
    #     )

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

    async def _process_response(self, content: str, reasoning_content: str) -> str:
        """处理响应内容，返回处理后的内容和情感标签"""
        if not content:
            return None

        # 清理输出中的括号注释内容
        cleaned_content = re.sub(r'\s*\([^\(\)]*字[^\(\)]*\)', '', content)
        cleaned_content = re.sub(r'\s*\([^\(\)]*字符[^\(\)]*\)', '', cleaned_content)
        cleaned_content = re.sub(r'\s*\([^\(\)]*保持.*?语气[^\(\)]*\)', '', cleaned_content)
        cleaned_content = re.sub(r'\s*\([^\(\)]*?:?包含.*?信息[^\(\)]*\)', '', cleaned_content)
        
        # 如果清理后为空，则使用原始响应
        if not cleaned_content.strip():
            cleaned_content = content

        # 执行原有的处理逻辑
        processed_response = process_llm_response(cleaned_content)

        # 匹配并处理表情标记
        emotion_pattern = r"^\[([^\[\]]*)\]\s*(.*)"
        match_emotion = re.match(emotion_pattern, processed_response)
        
        if match_emotion:
            emotion = match_emotion.group(1)
            content = match_emotion.group(2)
            
            # 大概率随机移除表情
            remove_emotion = random.random() < 0.7  
            
            if remove_emotion:
                processed_response = content

        return processed_response

    def _format_response(self, response: str) -> List[str]:
        # 实现格式化响应的逻辑
        # 这里需要根据实际需求来实现
        return [response]
