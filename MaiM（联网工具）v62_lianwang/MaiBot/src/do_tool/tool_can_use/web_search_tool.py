from src.do_tool.tool_can_use.base_tool import BaseTool
from src.common.logger import get_module_logger
from typing import Dict, Any, List, Tuple
from src.plugins.web_search import WebSearcher
import asyncio
import re
import time
import os
from datetime import datetime

logger = get_module_logger("web_search_tool")


class WebSearchTool(BaseTool):
    """网络搜索工具"""

    name = "web_search"
    description = "搜索网络以获取有关特定主题或问题的最新信息，支持时间范围限制"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "要搜索的查询内容"},
            "num_results": {"type": "integer", "description": "返回的搜索结果数量，默认为10"},
            "time_range": {"type": "string", "description": "搜索结果的时间范围，可选值: day, week, month, year，默认为month"},
            "force_search": {"type": "boolean", "description": "是否强制执行搜索，忽略冷却时间，默认为false"},
            "chat_id": {"type": "string", "description": "聊天ID，用于搜索冷却控制"}
        },
        "required": ["query"],
    }

    def __init__(self):
        """初始化网络搜索工具"""
        # 创建WebSearcher实例，使用默认配置
        self.searcher = WebSearcher()
        # 创建结果缓存
        self._cache = {}
        # 添加搜索冷却时间记录
        self._last_search_times = {}
        # 默认冷却时间(秒)
        self.default_cooldown = 600  # 10分钟

    async def execute(self, function_args: Dict[str, Any], message_txt: str = "") -> Dict[str, Any]:
        """执行网络搜索

        Args:
            function_args: 工具参数
            message_txt: 原始消息文本

        Returns:
            Dict: 工具执行结果
        """
        try:
            query = function_args.get("query")
            num_results = function_args.get("num_results", 10)
            time_range = function_args.get("time_range", "month")
            force_search = function_args.get("force_search", False)
            chat_id = function_args.get("chat_id", "")
            
            # 检查冷却时间（除非强制搜索）
            if not force_search and chat_id:
                cooldown_result = self._check_cooldown(chat_id)
                if not cooldown_result[0]:  # 冷却中
                    logger.info(f"搜索冷却中，剩余时间:{cooldown_result[1]:.1f}秒")
                    return {"name": self.name, "content": f"搜索冷却中，剩余{cooldown_result[1]:.1f}秒", "skipped": True, "reason": "冷却中"}
            
            # 检查是否有缓存结果(5分钟内的相同查询)
            cache_key = f"{query}:{time_range}:{num_results}"
            current_time = asyncio.get_event_loop().time()
            if cache_key in self._cache:
                # 检查缓存是否仍然有效(5分钟内)
                cache_time, cached_results = self._cache[cache_key]
                if current_time - cache_time < 300:  # 5分钟 = 300秒
                    logger.info(f"使用缓存结果，查询: {query}")
                    return {"name": self.name, "content": cached_results, "from_cache": True}
            
            # 更新搜索结果数量
            self.searcher.num_results = num_results
            
            # 更新最后搜索时间
            if chat_id:
                self._last_search_times[chat_id] = current_time
            
            # 执行搜索
            logger.info(f"执行搜索，查询: {query}, 时间范围: {time_range}")
            results = await self.searcher.search_web(query, time_range=time_range)
            
            # 格式化结果
            formatted_results = self.searcher.format_results(results)
            
            # 增强结果展示
            enhanced_results = self._enhance_search_results(formatted_results, query)
            
            # 缓存结果
            self._cache[cache_key] = (current_time, enhanced_results)
            
            # 清理过期缓存
            self._clean_cache()
            
            return {"name": self.name, "content": enhanced_results}
        except Exception as e:
            logger.error(f"网络搜索失败: {str(e)}")
            return {"name": self.name, "content": f"网络搜索失败: {str(e)}"}
    
    def _enhance_search_results(self, results: str, query: str) -> str:
        """增强搜索结果展示
        
        Args:
            results: 原始格式化结果
            query: 搜索查询
            
        Returns:
            str: 增强后的结果
        """
        # 添加时间戳
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # 检查结果是否为空
        if "没有找到相关结果" in results:
            return f"【{current_time}】搜索「{query}」：未找到相关结果。"
        
        # 添加简短前缀
        enhanced = f"【{current_time}】搜索「{query}」的结果:\n\n{results}"
        
        return enhanced
            
    def _clean_cache(self):
        """清理过期缓存"""
        current_time = asyncio.get_event_loop().time()
        expired_keys = []
        for key, (cache_time, _) in self._cache.items():
            if current_time - cache_time > 300:  # 5分钟过期
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._cache[key]
    
    def _check_cooldown(self, chat_id: str) -> Tuple[bool, float]:
        """检查搜索冷却时间
        
        Args:
            chat_id: 聊天ID
            
        Returns:
            Tuple[bool, float]: (是否可以搜索, 剩余冷却时间)
        """
        current_time = asyncio.get_event_loop().time()
        cooldown_seconds = float(os.getenv('SEARCH_COOLDOWN_SECONDS', str(self.default_cooldown)))
        
        if chat_id in self._last_search_times:
            last_time = self._last_search_times[chat_id]
            elapsed = current_time - last_time
            
            if elapsed < cooldown_seconds:
                # 还在冷却中
                remaining = cooldown_seconds - elapsed
                return False, remaining
        
        # 已经冷却完成或没有记录
        return True, 0.0 