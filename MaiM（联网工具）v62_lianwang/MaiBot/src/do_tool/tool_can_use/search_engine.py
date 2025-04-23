from src.do_tool.tool_can_use.base_tool import BaseTool, register_tool
from src.plugins.chat.utils import get_embedding
from src.common.database import db
from src.common.logger import get_module_logger
from typing import Dict, Any, List, Optional, Tuple, Set
from datetime import datetime
import json
import re
import time
from src.common.utils import log_async_performance, PerformanceTimer
import math
import asyncio

logger = get_module_logger("search_engine_tool")


class SearchEngineTool(BaseTool):
    """搜索引擎工具，集成知识库和网络搜索"""

    name = "search_engine"
    description = "执行搜索，集成知识库和网络搜索结果"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询"},
            "chat_id": {"type": "string", "description": "聊天ID"},
            "prioritize_recent": {"type": "boolean", "description": "是否优先返回较新的结果"},
            "min_similarity": {"type": "number", "description": "最小相似度阈值"},
            "result_limit": {"type": "integer", "description": "结果数量限制"}
        },
        "required": ["query"]
    }

    def _extract_keywords_as_tags(self, text, existing_tags=None):
        """从文本中提取关键词作为标签"""
        if existing_tags is None:
            existing_tags = []
            
        try:
            # 预定义的停用词列表
            stopwords = ["的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这", "什么", "没", "这个", "可以", "但", "这些", "那", "大", "来", "这样", "因为", "里", "让", "她", "他", "它", "做", "被", "所以", "还", "能", "给", "我们", "你们", "他们", "她们", "因此", "如此", "如何"]
            
            # 分词
            import jieba
            words = jieba.cut(text)
            
            # 统计词频，过滤停用词和短词
            word_freq = {}
            for word in words:
                word = word.strip().lower()
                if word and len(word) > 1 and word not in stopwords and word not in existing_tags:
                    word_freq[word] = word_freq.get(word, 0) + 1
            
            # 按频率排序并取前5个
            keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
            
            # 转换为标签
            result_tags = [keyword for keyword, _ in keywords if len(keyword) > 1]
            logger.info(f"提取的关键词标签: {result_tags}")
            
            return result_tags
            
        except Exception as e:
            logger.error(f"提取关键词标签失败: {e}")
            return []

    async def execute(self, params):
        """执行搜索，集成知识库和网络搜索"""
        try:
            # 记录开始时间
            with timer.start_section("search_engine_execute"):
                query = params.get("query", "")
                chat_id = params.get("chat_id", "")
                prioritize_recent = params.get("prioritize_recent", True)
                min_similarity = params.get("min_similarity", 0.5)
                result_limit = params.get("result_limit", 5)
                
                # 检查缓存
                with timer.start_section("check_cache"):
                    cache_key = f"search:{query}"
                    cached_result = self._get_cache(cache_key)
                    if cached_result:
                        logger.info(f"返回缓存的搜索结果，查询: {query}")
                        return cached_result
                
                # 检查冷却时间
                with timer.start_section("check_cooldown"):
                    if not self._check_cooldown():
                        logger.info("搜索引擎冷却中，跳过本次搜索")
                        return {
                            "skipped": True, 
                            "reason": "cooldown",
                            "content": "搜索引擎冷却中，请稍后再试"
                        }
                
                # 首先尝试从知识库查询
                knowledge_results = None
                with timer.start_section("search_knowledge"):
                    if global_config.enable_knowledge_base_search:
                        knowledge_results = await self._search_knowledge(query, min_similarity)
                    else:
                        logger.info("知识库查询已禁用，跳过知识库搜索")
                
                # 判断是否需要网络搜索
                need_web_search = False
                with timer.start_section("decide_web_search"):
                    if self._should_do_web_search(query, knowledge_results):
                        need_web_search = True
                
                # 进行网络搜索
                web_results = None
                if need_web_search:
                    with timer.start_section("web_search"):
                        web_results = await self._do_web_search(query)
                
                # 存储网络搜索结果到知识库
                with timer.start_section("store_knowledge"):
                    if web_results and global_config.enable_knowledge_base_search:
                        formatted_results = self._format_web_results(web_results)
                        
                        # 基本标签
                        tags = ["search_result", "web_source"]
                        
                        # 添加时间敏感标签
                        if any(word in query.lower() for word in ["最新", "最近", "今日", "本周"]):
                            tags.append("time_sensitive")
                        
                        # 提取关键词作为标签
                        keyword_tags = self._extract_keywords_as_tags(query + " " + formatted_results, tags)
                        tags.extend(keyword_tags)
                        
                        # 设置重要性
                        importance = 3  # 默认中等重要性
                        if any(tag in ["time_sensitive"] for tag in tags):
                            importance = 4  # 时效性内容更重要
                            
                        # 存储到知识库
                        await self._store_to_knowledge_base(
                            query=query, 
                            content=f"【{time.strftime('%Y-%m-%d %H:%M', time.localtime())}】搜索「{query}」的结果:\n\n{formatted_results}",
                            tags=tags,
                            importance=importance
                        )
                
                # 组合结果
                combined_result = {}
                with timer.start_section("combine_results"):
                    if knowledge_results and web_results:
                        # 两种结果都有时，进行结果融合
                        combined_result = self._combine_search_results(knowledge_results, web_results, query)
                    elif knowledge_results:
                        # 只有知识库结果
                        combined_result = {
                            "content": knowledge_results,
                            "source": "knowledge_base",
                            "tags": self._extract_keywords_as_tags(query + " " + knowledge_results)
                        }
                    elif web_results:
                        # 只有网络搜索结果
                        formatted_web = self._format_web_results(web_results)
                        combined_result = {
                            "content": formatted_web,
                            "source": "web_search",
                            "web_search_used": True,
                            "tags": self._extract_keywords_as_tags(query + " " + formatted_web)
                        }
                    else:
                        # 没有任何结果
                        combined_result = {
                            "content": "抱歉，我没有找到与您问题相关的信息。",
                            "source": "none",
                            "tags": []
                        }
                
                # 缓存结果
                with timer.start_section("cache_results"):
                    self._set_cache(cache_key, combined_result)
                
                return combined_result
                
        except Exception as e:
            logger.error(f"搜索引擎执行失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                "error": str(e),
                "content": "搜索过程中出现错误，请稍后再试"
            } 