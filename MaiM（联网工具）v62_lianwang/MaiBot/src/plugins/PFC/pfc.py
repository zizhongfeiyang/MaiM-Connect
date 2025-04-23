# Programmable Friendly Conversationalist
# Prefrontal cortex
import datetime

# import asyncio
from typing import List, Optional, Tuple, TYPE_CHECKING
from src.common.logger import get_module_logger
from ..chat.chat_stream import ChatStream
from ..message.message_base import UserInfo, Seg
from ..chat.message import Message
from ..models.utils_model import LLM_request
from ..config.config import global_config
from src.plugins.chat.message import MessageSending
from ..message.api import global_api
from ..storage.storage import MessageStorage
from .chat_observer import ChatObserver
from .pfc_utils import get_items_from_json
from src.individuality.individuality import Individuality
from .conversation_info import ConversationInfo
from .observation_info import ObservationInfo
import time

if TYPE_CHECKING:
    pass

logger = get_module_logger("pfc")


class GoalAnalyzer:
    """对话目标分析器"""

    def __init__(self, stream_id: str):
        self.llm = LLM_request(
            model=global_config.llm_normal, temperature=0.7, max_tokens=1000, request_type="conversation_goal"
        )

        self.personality_info = Individuality.get_instance().get_prompt(type="personality", x_person=2, level=2)
        self.name = global_config.BOT_NICKNAME
        self.nick_name = global_config.BOT_ALIAS_NAMES
        self.chat_observer = ChatObserver.get_instance(stream_id)

        # 多目标存储结构
        self.goals = []  # 存储多个目标
        self.max_goals = 3  # 同时保持的最大目标数量
        self.current_goal_and_reason = None

    async def analyze_goal(self, conversation_info: ConversationInfo, observation_info: ObservationInfo):
        """分析对话历史并设定目标

        Args:
            conversation_info: 对话信息
            observation_info: 观察信息

        Returns:
            Tuple[str, str, str]: (目标, 方法, 原因)
        """
        # 构建对话目标
        goals_str = ""
        if conversation_info.goal_list:
            for goal_reason in conversation_info.goal_list:
                # 处理字典或元组格式
                if isinstance(goal_reason, tuple):
                    # 假设元组的第一个元素是目标，第二个元素是原因
                    goal = goal_reason[0]
                    reasoning = goal_reason[1] if len(goal_reason) > 1 else "没有明确原因"
                elif isinstance(goal_reason, dict):
                    goal = goal_reason.get("goal")
                    reasoning = goal_reason.get("reasoning", "没有明确原因")
                else:
                    # 如果是其他类型，尝试转为字符串
                    goal = str(goal_reason)
                    reasoning = "没有明确原因"

                goal_str = f"目标：{goal}，产生该对话目标的原因：{reasoning}\n"
                goals_str += goal_str
        else:
            goal = "目前没有明确对话目标"
            reasoning = "目前没有明确对话目标，最好思考一个对话目标"
            goals_str = f"目标：{goal}，产生该对话目标的原因：{reasoning}\n"

        # 获取聊天历史记录
        chat_history_list = observation_info.chat_history
        chat_history_text = ""
        for msg in chat_history_list:
            chat_history_text += f"{msg}\n"

        if observation_info.new_messages_count > 0:
            new_messages_list = observation_info.unprocessed_messages

            chat_history_text += f"有{observation_info.new_messages_count}条新消息：\n"
            for msg in new_messages_list:
                chat_history_text += f"{msg}\n"

            observation_info.clear_unprocessed_messages()

        personality_text = f"你的名字是{self.name}，{self.personality_info}"

        # 构建action历史文本
        action_history_list = conversation_info.done_action
        action_history_text = "你之前做的事情是："
        for action in action_history_list:
            action_history_text += f"{action}\n"

        prompt = f"""{personality_text}。现在你在参与一场QQ聊天，请分析以下聊天记录，并根据你的性格特征确定多个明确的对话目标。
这些目标应该反映出对话的不同方面和意图。

{action_history_text}
当前对话目标：
{goals_str}

聊天记录：
{chat_history_text}

请分析当前对话并确定最适合的对话目标。你可以：
1. 保持现有目标不变
2. 修改现有目标
3. 添加新目标
4. 删除不再相关的目标
5. 如果你想结束对话，请设置一个目标，目标goal为"结束对话"，原因reasoning为你希望结束对话

请以JSON数组格式输出当前的所有对话目标，每个目标包含以下字段：
1. goal: 对话目标（简短的一句话）
2. reasoning: 对话原因，为什么设定这个目标（简要解释）

输出格式示例：
[
  {{
    "goal": "回答用户关于Python编程的具体问题",
    "reasoning": "用户提出了关于Python的技术问题，需要专业且准确的解答"
  }},
  {{
    "goal": "回答用户关于python安装的具体问题",
    "reasoning": "用户提出了关于Python的技术问题，需要专业且准确的解答"
  }}
]"""

        logger.debug(f"发送到LLM的提示词: {prompt}")
        try:
            content, _ = await self.llm.generate_response_async(prompt)
            logger.debug(f"LLM原始返回内容: {content}")
        except Exception as e:
            logger.error(f"分析对话目标时出错: {str(e)}")
            content = ""

        # 使用改进后的get_items_from_json函数处理JSON数组
        success, result = get_items_from_json(
            content, "goal", "reasoning", required_types={"goal": str, "reasoning": str}, allow_array=True
        )

        if success:
            # 判断结果是单个字典还是字典列表
            if isinstance(result, list):
                # 清空现有目标列表并添加新目标
                conversation_info.goal_list = []
                for item in result:
                    goal = item.get("goal", "")
                    reasoning = item.get("reasoning", "")
                    conversation_info.goal_list.append((goal, reasoning))

                # 返回第一个目标作为当前主要目标（如果有）
                if result:
                    first_goal = result[0]
                    return (first_goal.get("goal", ""), "", first_goal.get("reasoning", ""))
            else:
                # 单个目标的情况
                goal = result.get("goal", "")
                reasoning = result.get("reasoning", "")
                conversation_info.goal_list.append((goal, reasoning))
                return (goal, "", reasoning)

        # 如果解析失败，返回默认值
        return ("", "", "")

    async def _update_goals(self, new_goal: str, method: str, reasoning: str):
        """更新目标列表

        Args:
            new_goal: 新的目标
            method: 实现目标的方法
            reasoning: 目标的原因
        """
        # 检查新目标是否与现有目标相似
        for i, (existing_goal, _, _) in enumerate(self.goals):
            if self._calculate_similarity(new_goal, existing_goal) > 0.7:  # 相似度阈值
                # 更新现有目标
                self.goals[i] = (new_goal, method, reasoning)
                # 将此目标移到列表前面（最主要的位置）
                self.goals.insert(0, self.goals.pop(i))
                return

        # 添加新目标到列表前面
        self.goals.insert(0, (new_goal, method, reasoning))

        # 限制目标数量
        if len(self.goals) > self.max_goals:
            self.goals.pop()  # 移除最老的目标

    def _calculate_similarity(self, goal1: str, goal2: str) -> float:
        """简单计算两个目标之间的相似度

        这里使用一个简单的实现，实际可以使用更复杂的文本相似度算法

        Args:
            goal1: 第一个目标
            goal2: 第二个目标

        Returns:
            float: 相似度得分 (0-1)
        """
        # 简单实现：检查重叠字数比例
        words1 = set(goal1)
        words2 = set(goal2)
        overlap = len(words1.intersection(words2))
        total = len(words1.union(words2))
        return overlap / total if total > 0 else 0

    async def get_all_goals(self) -> List[Tuple[str, str, str]]:
        """获取所有当前目标

        Returns:
            List[Tuple[str, str, str]]: 目标列表，每项为(目标, 方法, 原因)
        """
        return self.goals.copy()

    async def get_alternative_goals(self) -> List[Tuple[str, str, str]]:
        """获取除了当前主要目标外的其他备选目标

        Returns:
            List[Tuple[str, str, str]]: 备选目标列表
        """
        if len(self.goals) <= 1:
            return []
        return self.goals[1:].copy()

    async def analyze_conversation(self, goal, reasoning):
        messages = self.chat_observer.get_cached_messages()
        chat_history_text = ""
        for msg in messages:
            time_str = datetime.datetime.fromtimestamp(msg["time"]).strftime("%H:%M:%S")
            user_info = UserInfo.from_dict(msg.get("user_info", {}))
            sender = user_info.user_nickname or f"用户{user_info.user_id}"
            if sender == self.name:
                sender = "你说"
            chat_history_text += f"{time_str},{sender}:{msg.get('processed_plain_text', '')}\n"

        personality_text = f"你的名字是{self.name}，{self.personality_info}"

        prompt = f"""{personality_text}。现在你在参与一场QQ聊天，
        当前对话目标：{goal}
        产生该对话目标的原因：{reasoning}
        
        请分析以下聊天记录，并根据你的性格特征评估该目标是否已经达到，或者你是否希望停止该次对话。
        聊天记录：
        {chat_history_text}
        请以JSON格式输出，包含以下字段：
        1. goal_achieved: 对话目标是否已经达到（true/false）
        2. stop_conversation: 是否希望停止该次对话（true/false）
        3. reason: 为什么希望停止该次对话（简要解释）   

输出格式示例：
{{
    "goal_achieved": true,
    "stop_conversation": false,
    "reason": "虽然目标已达成，但对话仍然有继续的价值"
}}"""

        try:
            content, _ = await self.llm.generate_response_async(prompt)
            logger.debug(f"LLM原始返回内容: {content}")

            # 尝试解析JSON
            success, result = get_items_from_json(
                content,
                "goal_achieved",
                "stop_conversation",
                "reason",
                required_types={"goal_achieved": bool, "stop_conversation": bool, "reason": str},
            )

            if not success:
                logger.error("无法解析对话分析结果JSON")
                return False, False, "解析结果失败"

            goal_achieved = result["goal_achieved"]
            stop_conversation = result["stop_conversation"]
            reason = result["reason"]

            return goal_achieved, stop_conversation, reason

        except Exception as e:
            logger.error(f"分析对话状态时出错: {str(e)}")
            return False, False, f"分析出错: {str(e)}"


class DirectMessageSender:
    """直接发送消息到平台的发送器"""

    def __init__(self):
        self.logger = get_module_logger("direct_sender")
        self.storage = MessageStorage()

    async def send_via_ws(self, message: MessageSending) -> None:
        try:
            await global_api.send_message(message)
        except Exception as e:
            raise ValueError(f"未找到平台：{message.message_info.platform} 的url配置，请检查配置文件") from e

    async def send_message(
        self,
        chat_stream: ChatStream,
        content: str,
        reply_to_message: Optional[Message] = None,
    ) -> None:
        """直接发送消息到平台

        Args:
            chat_stream: 聊天流
            content: 消息内容
            reply_to_message: 要回复的消息
        """
        # 构建消息对象
        message_segment = Seg(type="text", data=content)
        bot_user_info = UserInfo(
            user_id=global_config.BOT_QQ,
            user_nickname=global_config.BOT_NICKNAME,
            platform=chat_stream.platform,
        )

        message = MessageSending(
            message_id=f"dm{round(time.time(), 2)}",
            chat_stream=chat_stream,
            bot_user_info=bot_user_info,
            sender_info=reply_to_message.message_info.user_info if reply_to_message else None,
            message_segment=message_segment,
            reply=reply_to_message,
            is_head=True,
            is_emoji=False,
            thinking_start_time=time.time(),
        )

        # 处理消息
        await message.process()

        message_json = message.to_dict()

        # 发送消息
        try:
            end_point = global_config.api_urls.get(message.message_info.platform, None)
            if end_point:
                # logger.info(f"发送消息到{end_point}")
                # logger.info(message_json)
                try:
                    await global_api.send_message_REST(end_point, message_json)
                except Exception as e:
                    logger.error(f"REST方式发送失败，出现错误: {str(e)}")
                    logger.info("尝试使用ws发送")
                    await self.send_via_ws(message)
            else:
                await self.send_via_ws(message)
            logger.success(f"PFC消息已发送: {content}")
        except Exception as e:
            logger.error(f"PFC消息发送失败: {str(e)}")
