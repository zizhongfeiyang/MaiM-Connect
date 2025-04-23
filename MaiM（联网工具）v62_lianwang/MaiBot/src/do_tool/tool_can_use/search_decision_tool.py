from src.do_tool.tool_can_use.base_tool import BaseTool
from src.common.logger import get_module_logger
from typing import Dict, Any, Tuple
import re
import asyncio
import json

logger = get_module_logger("search_decision_tool")


class SearchDecisionTool(BaseTool):
    """搜索决策工具，用于判断是否需要进行网络搜索"""

    name = "search_decision"
    description = "分析用户消息决定是否需要执行网络搜索，避免不必要的搜索"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "要分析的查询内容或用户消息"},
            "message_txt": {"type": "string", "description": "完整的原始消息文本，提供更多上下文"},
            "response_quality": {"type": "string", "description": "当前回复的质量评估，用于判断回复是否已足够"},
            "force_search": {"type": "boolean", "description": "是否强制搜索，忽略决策过程，默认为false"},
            "use_llm": {"type": "boolean", "description": "是否在规则判断不确定时使用大模型辅助决策，默认为true"}
        },
        "required": ["query"],
    }

    def __init__(self):
        """初始化搜索决策工具"""
        pass

    async def execute(self, function_args: Dict[str, Any], message_txt: str = "") -> Dict[str, Any]:
        """执行搜索决策分析

        Args:
            function_args: 工具参数
            message_txt: 原始消息文本

        Returns:
            Dict: 工具执行结果，包含是否需要搜索的决策和理由
        """
        try:
            query = function_args.get("query", "")
            message_text = function_args.get("message_txt", message_txt)  # 使用参数中的message_txt或传入的message_txt
            response_quality = function_args.get("response_quality", "")
            force_search = function_args.get("force_search", False)
            use_llm = function_args.get("use_llm", True)
            
            # 如果强制搜索，则直接返回需要搜索
            if force_search:
                decision_content = "用户强制要求搜索"
                return {
                    "name": self.name, 
                    "need_search": True, 
                    "reason": "用户强制要求搜索",
                    "content": decision_content,
                    "decision_method": "rule"
                }
            
            # 首先使用高置信度规则进行判断
            high_confidence_result = self._check_high_confidence_rules(query, message_text, response_quality)
            if high_confidence_result is not None:
                need_search, reason = high_confidence_result
                decision_method = "rule_high_confidence"
            else:
                # 如果启用LLM决策且高置信度规则无法判断
                if use_llm:
                    # 尝试使用LLM进行决策
                    llm_result = await self._llm_analyze_search_need(query, message_text)
                    if llm_result is not None:
                        need_search, reason = llm_result
                        decision_method = "llm"
                    else:
                        # 如果LLM决策失败，回退到一般规则
                        need_search, reason = self._check_general_rules(query, message_text)
                        decision_method = "rule_fallback"
                else:
                    # 未启用LLM，直接使用一般规则
                    need_search, reason = self._check_general_rules(query, message_text)
                    decision_method = "rule"
            
            # 创建更人性化的决策内容
            if need_search:
                decision_content = f"需要为用户搜索信息，原因是：{reason}"
            else:
                decision_content = f"不需要搜索，原因是：{reason}"
                
            logger.info(f"{decision_content} (决策方法: {decision_method})")
            
            return {
                "name": self.name,
                "need_search": need_search,
                "reason": reason,
                "content": decision_content,
                "decision_method": decision_method
            }
            
        except Exception as e:
            error_msg = f"搜索决策分析失败: {str(e)}"
            logger.error(error_msg)
            # 出错时默认不搜索
            return {
                "name": self.name,
                "need_search": False,
                "reason": f"决策过程出错: {str(e)}",
                "content": error_msg,
                "decision_method": "error"
            }
    
    def _check_high_confidence_rules(self, query: str, message_txt: str = "", response_quality: str = "") -> Tuple[bool, str]:
        """检查高置信度规则
        
        Args:
            query: 搜索查询
            message_txt: 原始消息
            response_quality: 回复质量评估
            
        Returns:
            Tuple[bool, str] or None: (需要搜索, 理由) 或 None (表示无法确定)
        """
        text_to_analyze = message_txt or query
        
        # 1. 检查是否强制搜索（用户明确要求）- 高置信度情况
        search_keywords = ["搜索", "查一下", "查一查", "查找", "查询", "搜一下", "搜一搜", 
                           "百度", "谷歌", "找找看"]
        if any(keyword in text_to_analyze for keyword in search_keywords):
            return True, "用户明确要求搜索"
        
        # 2. 检查明确的情感表达 - 高置信度情况
        clear_emotion_phrases = [
            "好想你", "我想你", "想你了", "思念你", "我爱你", "爱你", 
            "想念你", "我很想你"
        ]
        
        # 检查文本中是否包含完整的情感表达
        if any(phrase in text_to_analyze for phrase in clear_emotion_phrases):
            return False, "明确的情感表达消息"
        
        # 检查非常明确的昵称+情感词组合
        nickname_match = re.search(r"(小飞|飞飞|阿飞|宝贝|亲爱的)", text_to_analyze)
        emotion_match = re.search(r"(好想|想你|爱你|喜欢你|思念|想念)", text_to_analyze)
        if nickname_match and emotion_match:
            return False, "针对机器人的情感表达"
        
        # 3. 明确的简短问候 - 高置信度情况
        greeting_patterns = [
            r"^你好[啊吗呀呢]*[~！!?？]*$", 
            r"^早上好[啊吗呀呢]*[~！!?？]*$", 
            r"^晚上好[啊吗呀呢]*[~！!?？]*$",
            r"^谢谢[啊吗呀呢]*[~！!?？]*$"
        ]
        if any(re.match(pattern, text_to_analyze) for pattern in greeting_patterns):
            return False, "简单问候"
        
        # 如果没有匹配到高置信度规则，返回None表示需要进一步判断
        return None
    
    def _check_general_rules(self, query: str, message_txt: str = "") -> Tuple[bool, str]:
        """检查一般规则
        
        Args:
            query: 搜索查询
            message_txt: 原始消息
            
        Returns:
            Tuple[bool, str]: (需要搜索, 理由)
        """
        text_to_analyze = message_txt or query
        
        # 1. 检查信息需求 - 合并了原来的信息需求和专业知识需求
        info_keywords = [
            "怎么", "如何", "什么", "哪些", "为什么", "多少", "谁", "哪里",
            "技术", "科技", "学术", "研究", "方法", "原理", "系统", 
            "算法", "模型", "理论", "概念", "定义"
        ]
        
        # 使用更精确的词语匹配方式，避免误判
        # 例如，检查"什么"是否作为独立词出现，而不是词组的一部分
        for keyword in info_keywords:
            if re.search(rf'\b{keyword}\b', text_to_analyze):
                return True, "信息或知识需求"
        
        # 2. 检查时间敏感性
        time_keywords = ["今天", "昨天", "最近", "最新", "现在", "新闻", "消息", "动态"]
        for keyword in time_keywords:
            if keyword in text_to_analyze:
                return True, "时间敏感信息需求"
        
        # 3. 消息长度检查
        if len(text_to_analyze) < 10:
            return False, "消息过短"
        
        # 4. 默认不搜索
        return False, "默认策略" 
    
    async def _llm_analyze_search_need(self, query: str, message_txt: str = "") -> Tuple[bool, str]:
        """使用LLM分析是否需要搜索
        
        Args:
            query: 搜索查询
            message_txt: 原始消息
            
        Returns:
            Tuple[bool, str] or None: (需要搜索, 理由) 或 None表示分析失败
        """
        try:
            # 导入模型
            from src.plugins.chat.model_normal import model_normal
            
            text_to_analyze = message_txt or query
            
            # 构建分析提示词
            prompt = f"""分析以下用户消息，判断是否需要执行网络搜索来回答。

用户消息: "{text_to_analyze}"

需要考虑的因素:
1. 如果是问候语、情感表达(如"想你"、"爱你"、"你好")，不需要搜索
2. 如果询问事实信息、新闻、时事或专业知识，需要搜索
3. 如果是闲聊、感慨或情感交流，不需要搜索
4. 如果包含明显的搜索意图词(如"搜索"、"查一下")，需要搜索

你的回答必须是有效的JSON格式，仅包含以下字段:
{{"need_search": true/false, "reason": "简短理由(20字以内)"}}
"""
            
            # 调用模型分析
            response = await model_normal.generate_response(prompt)
            
            if response and len(response) > 0:
                # 提取JSON响应
                try:
                    # 确保获取到有效的JSON
                    json_text = response[0].strip()
                    # 如果有多余的文本包裹着JSON，尝试提取
                    if not json_text.startswith('{'):
                        json_match = re.search(r'({.*})', json_text, re.DOTALL)
                        if json_match:
                            json_text = json_match.group(1)
                    
                    result = json.loads(json_text)
                    need_search = result.get("need_search", False)
                    reason = result.get("reason", "LLM分析结果")
                    
                    logger.info(f"LLM分析结果: 需要搜索={need_search}, 理由={reason}")
                    return need_search, reason
                except json.JSONDecodeError as e:
                    logger.error(f"LLM返回结果解析失败: {e}, 原始响应: {response[0]}")
                    return None
            
            # 如果无法获取有效响应
            logger.warning("LLM返回了空响应或无效响应")
            return None
            
        except Exception as e:
            logger.error(f"LLM分析过程出错: {str(e)}")
            return None
            
    def _analyze_search_need(self, query: str, message_txt: str = "", response_quality: str = "") -> Tuple[bool, str]:
        """分析是否需要执行搜索(兼容旧接口，重定向到新的决策流程)
        
        Args:
            query: 搜索查询
            message_txt: 原始消息
            response_quality: 回复质量评估
            
        Returns:
            tuple: (需要搜索, 理由)
        """
        # 首先检查高置信度规则
        high_confidence_result = self._check_high_confidence_rules(query, message_txt, response_quality)
        if high_confidence_result is not None:
            return high_confidence_result
        
        # 如果高置信度规则无法判断，使用一般规则
        return self._check_general_rules(query, message_txt) 