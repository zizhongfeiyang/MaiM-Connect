from ..moods.moods import MoodManager  # 导入情绪管理器
from ..config.config import global_config
from .message import MessageRecv
from ..PFC.pfc_manager import PFCManager
from .chat_stream import chat_manager
from ..chat_module.only_process.only_message_process import MessageProcessor
from src.do_tool.tool_can_use import get_tool_instance

from src.common.logger import get_module_logger, CHAT_STYLE_CONFIG, LogConfig
from ..chat_module.think_flow_chat.think_flow_chat import ThinkFlowChat
from ..chat_module.reasoning_chat.reasoning_chat import ReasoningChat
from ..utils.prompt_builder import Prompt, global_prompt_manager
import traceback

# 定义日志配置
chat_config = LogConfig(
    # 使用消息发送专用样式
    console_format=CHAT_STYLE_CONFIG["console_format"],
    file_format=CHAT_STYLE_CONFIG["file_format"],
)

# 配置主程序日志格式
logger = get_module_logger("chat_bot", config=chat_config)


class ChatBot:
    def __init__(self):
        self.bot = None  # bot 实例引用
        self._started = False
        self.mood_manager = MoodManager.get_instance()  # 获取情绪管理器单例
        self.mood_manager.start_mood_update()  # 启动情绪更新
        self.think_flow_chat = ThinkFlowChat()
        self.reasoning_chat = ReasoningChat()
        self.only_process_chat = MessageProcessor()

        # 创建初始化PFC管理器的任务，会在_ensure_started时执行
        self.pfc_manager = PFCManager.get_instance()

    async def _ensure_started(self):
        """确保所有任务已启动"""
        if not self._started:
            logger.trace("确保ChatBot所有任务已启动")

            self._started = True

    async def _create_PFC_chat(self, message: MessageRecv):
        try:
            chat_id = str(message.chat_stream.stream_id)

            if global_config.enable_pfc_chatting:
                await self.pfc_manager.get_or_create_conversation(chat_id)

        except Exception as e:
            logger.error(f"创建PFC聊天失败: {e}")

    async def search_web(self, query: str) -> str:
        """
        执行网络搜索并返回结果
        :param query: 搜索查询
        :return: 格式化后的搜索结果
        """
        try:
            # 使用工具箱中的网络搜索工具
            web_search_tool = get_tool_instance("web_search")
            if not web_search_tool:
                logger.error("无法获取网络搜索工具，请确保工具已正确注册")
                return "抱歉，网络搜索工具未正确加载。"
                
            # 执行搜索
            result = await web_search_tool.execute({"query": query})
            
            if result and "content" in result:
                return result["content"]
            else:
                return "抱歉，没有找到相关结果。"
        except Exception as e:
            logger.error(f"网络搜索失败: {str(e)}")
            return "抱歉，搜索过程中出现了错误。"

    async def message_process(self, message_data: str) -> None:
        """
        处理接收到的消息
        :param message_data: 消息数据
        """
        try:
            message = MessageRecv(message_data)
            
            # 使用 chat_manager 创建或获取 chat_stream
            chat_stream = await chat_manager.get_or_create_stream(
                platform=message.message_info.platform,
                user_info=message.message_info.user_info,
                group_info=message.message_info.group_info
            )
            message.update_chat_stream(chat_stream)
            
            # 处理消息内容
            await message.process()
            
            # 检查是否包含搜索指令
            if message.processed_plain_text.startswith("搜索 ") or message.processed_plain_text.startswith("search "):
                query = message.processed_plain_text.replace("搜索 ", "").replace("search ", "")
                search_results = await self.search_web(query)
                await chat_manager.send_message(message.chat_stream.stream_id, search_results)
                return

            # 原有的消息处理逻辑
            await self._ensure_started()
            
            # 创建PFC聊天
            await self._create_PFC_chat(message)
            
            # 处理消息并获取回复
            await self.think_flow_chat.process_message(message_data)
            
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            traceback.print_exc()


# 创建全局ChatBot实例
chat_bot = ChatBot()
