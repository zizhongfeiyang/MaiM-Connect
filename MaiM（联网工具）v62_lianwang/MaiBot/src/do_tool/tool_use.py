from src.plugins.models.utils_model import LLM_request
from src.plugins.config.config import global_config
from src.plugins.chat.chat_stream import ChatStream
from src.common.database import db
import time
import json
from src.common.logger import get_module_logger, TOOL_USE_STYLE_CONFIG, LogConfig
from src.do_tool.tool_can_use import get_all_tool_definitions, get_tool_instance
from src.heart_flow.sub_heartflow import SubHeartflow
from src.common.utils import PerformanceTimer
import traceback
from typing import Dict, Any, List, Optional

tool_use_config = LogConfig(
    # 使用消息发送专用样式
    console_format=TOOL_USE_STYLE_CONFIG["console_format"],
    file_format=TOOL_USE_STYLE_CONFIG["file_format"],
)
logger = get_module_logger("tool_use", config=tool_use_config)


class ToolUser:
    def __init__(self):
        self.llm_model_tool = LLM_request(
            model=global_config.llm_tool_use, temperature=0.2, max_tokens=1000, request_type="tool_use"
        )

    async def _build_tool_prompt(
        self, message_txt: str, sender_name: str, chat_stream: ChatStream, subheartflow: SubHeartflow = None
    ):
        """构建工具使用的提示词

        Args:
            message_txt: 用户消息文本
            sender_name: 发送者名称
            chat_stream: 聊天流对象

        Returns:
            str: 构建好的提示词
        """
        if subheartflow:
            mid_memory_info = subheartflow.observations[0].mid_memory_info
            # print(f"intol111111111111111111111111111111111222222222222mid_memory_info：{mid_memory_info}")
        else:
            mid_memory_info = ""

        new_messages = list(
            db.messages.find({"chat_id": chat_stream.stream_id, "time": {"$gt": time.time()}}).sort("time", 1).limit(15)
        )
        new_messages_str = ""
        for msg in new_messages:
            if "detailed_plain_text" in msg:
                new_messages_str += f"{msg['detailed_plain_text']}"

        # 这些信息应该从调用者传入，而不是从self获取
        bot_name = global_config.BOT_NICKNAME
        prompt = ""
        prompt += mid_memory_info
        prompt += "你正在思考如何回复群里的消息。\n"
        prompt += f"你注意到{sender_name}刚刚说：{message_txt}\n"
        prompt += f"注意你就是{bot_name}，{bot_name}指的就是你。"

        prompt += "你现在需要对群里的聊天内容进行回复，现在选择工具来对消息和你的回复进行处理，你是否需要额外的信息，比如回忆或者搜寻已有的知识，改变关系和情感，或者了解你现在正在做什么。"
        return prompt

    def _define_tools(self):
        """获取所有已注册工具的定义

        Returns:
            list: 工具定义列表
        """
        return get_all_tool_definitions()

    async def _execute_tool_call(self, tool_call, message_txt: str):
        """执行特定的工具调用

        Args:
            tool_call: 工具调用对象
            message_txt: 原始消息文本

        Returns:
            dict: 工具调用结果
        """
        try:
            function_name = tool_call["function"]["name"]
            function_args = json.loads(tool_call["function"]["arguments"])

            # 获取对应工具实例
            tool_instance = get_tool_instance(function_name)
            if not tool_instance:
                logger.warning(f"未知工具名称: {function_name}")
                return None

            # 执行工具
            result = await tool_instance.execute(function_args, message_txt)
            if result:
                # 直接使用 function_name 作为 tool_type
                tool_type = function_name

                return {
                    "tool_call_id": tool_call["id"],
                    "role": "tool",
                    "name": function_name,
                    "type": tool_type,
                    "content": result["content"],
                }
            return None
        except Exception as e:
            logger.error(f"执行工具调用时发生错误: {str(e)}")
            return None

    async def use_tool(
        self, message_txt: str, sender_name: str, chat_stream: ChatStream, subheartflow: SubHeartflow = None
    ):
        """使用工具辅助思考，判断是否需要额外信息

        Args:
            message_txt: 用户消息文本
            sender_name: 发送者名称
            chat_stream: 聊天流对象

        Returns:
            dict: 工具使用结果，包含结构化的信息
        """
        try:
            # 构建提示词
            prompt = await self._build_tool_prompt(message_txt, sender_name, chat_stream, subheartflow)

            # 定义可用工具
            tools = self._define_tools()
            logger.trace(f"工具定义: {tools}")

            # 使用llm_model_tool发送带工具定义的请求
            payload = {
                "model": self.llm_model_tool.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": global_config.max_response_length,
                "tools": tools,
                "temperature": 0.2,
            }

            logger.trace(f"发送工具调用请求，模型: {self.llm_model_tool.model_name}")
            # 发送请求获取模型是否需要调用工具
            response = await self.llm_model_tool._execute_request(
                endpoint="/chat/completions", payload=payload, prompt=prompt
            )

            # 根据返回值数量判断是否有工具调用
            if len(response) == 3:
                content, reasoning_content, tool_calls = response
                # logger.info(f"工具思考: {tool_calls}")
                # logger.debug(f"工具思考: {content}")

                # 检查响应中工具调用是否有效
                if not tool_calls:
                    logger.debug("模型返回了空的tool_calls列表")
                    return {"used_tools": False}

                tool_calls_str = ""
                for tool_call in tool_calls:
                    tool_calls_str += f"{tool_call['function']['name']}\n"
                logger.info(f"根据:\n{prompt}\n模型请求调用{len(tool_calls)}个工具: {tool_calls_str}")
                tool_results = []
                structured_info = {}  # 动态生成键

                # 执行所有工具调用
                for tool_call in tool_calls:
                    result = await self._execute_tool_call(tool_call, message_txt)
                    if result:
                        tool_results.append(result)
                        # 使用工具名称作为键
                        tool_name = result["name"]
                        if tool_name not in structured_info:
                            structured_info[tool_name] = []
                        structured_info[tool_name].append({"name": result["name"], "content": result["content"]})

                # 如果有工具结果，返回结构化的信息
                if structured_info:
                    logger.info(f"工具调用收集到结构化信息: {json.dumps(structured_info, ensure_ascii=False)}")
                    return {"used_tools": True, "structured_info": structured_info}
            else:
                # 没有工具调用
                content, reasoning_content = response
                logger.debug("模型没有请求调用任何工具")

            # 如果没有工具调用或处理失败，直接返回原始思考
            return {
                "used_tools": False,
            }

        except Exception as e:
            logger.error(f"工具调用过程中出错: {str(e)}")
            return {
                "used_tools": False,
                "error": str(e),
            }

    async def execute_tool(function_call: Dict[str, Any], message_txt: str, mid: str, thinking_flow_id: Optional[str] = None) -> Dict[str, Any]:
        """执行工具调用
        
        Args:
            function_call (Dict[str, Any]): 工具调用信息，包含name和arguments字段
            message_txt (str): 消息文本
            mid (str): 消息ID
            thinking_flow_id (Optional[str]): 思考流ID
            
        Returns:
            Dict[str, Any]: 工具执行结果
        """
        # 获取函数名和参数
        function_name = function_call.get("name", "")
        function_arguments = function_call.get("arguments", {})
        
        logger.info(f"执行工具: {function_name}, 参数: {function_arguments}")
        
        with PerformanceTimer(f"execute_tool-{function_name}") as timer:
            try:
                # 解析参数，如果是字符串则尝试解析为JSON
                if isinstance(function_arguments, str):
                    try:
                        function_arguments = json.loads(function_arguments)
                    except json.JSONDecodeError:
                        logger.warning(f"无法解析工具参数为JSON: {function_arguments}")
                        return {"name": function_name, "content": "参数解析失败，请确保参数格式正确"}
                
                # 获取工具实例
                timer.start_section("get_tool_instance")
                tool = get_tool_instance(function_name)
                timer.end_section()
                
                if not tool:
                    logger.error(f"未找到工具: {function_name}")
                    return {"name": function_name, "content": f"未找到工具: {function_name}"}
                
                # 执行工具
                timer.start_section("tool_execution")
                result = await tool.execute(function_arguments, message_txt)
                timer.end_section()
                
                # 记录工具调用到思考流程（如果有）
                timer.start_section("record_tool_call")
                if thinking_flow_id:
                    try:
                        from src.heart_flow.thinking_flow import record_tool_call
                        await record_tool_call(
                            thinking_flow_id=thinking_flow_id,
                            tool_name=function_name,
                            tool_args=function_arguments,
                            tool_result=result
                        )
                    except Exception as e:
                        logger.error(f"记录工具调用到思考流程失败: {e}")
                timer.end_section()
                
                logger.info(f"工具执行完成: {function_name}")
                return result
                
            except Exception as e:
                error_message = f"工具执行异常: {str(e)}\n{traceback.format_exc()}"
                logger.error(error_message)
                return {"name": function_name, "content": f"工具执行失败: {str(e)}"}
