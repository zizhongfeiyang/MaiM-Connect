from src.do_tool.tool_can_use.base_tool import BaseTool
from src.common.logger import get_module_logger
from typing import Dict, Any, List, Optional, Union, Tuple
import asyncio
import time
import os
from datetime import datetime
import re
from src.common.utils import log_async_performance, PerformanceTimer

logger = get_module_logger("search_engine_tool")


class SearchEngineTool(BaseTool):
    """集成式搜索引擎工具，可智能判断是否使用知识库或执行网络搜索"""

    name = "search_engine"
    description = "智能搜索引擎，会先在知识库中查找信息，如果需要再执行网络搜索，自动存储有价值的信息"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "要搜索的查询内容"},
            "force_web_search": {"type": "boolean", "description": "是否强制执行网络搜索，默认为false"},
            "time_range": {"type": "string", "description": "搜索结果的时间范围，可选值: day, week, month, year，默认为month"},
            "num_results": {"type": "integer", "description": "返回的搜索结果数量，默认为5"},
            "chat_id": {"type": "string", "description": "聊天ID，用于搜索冷却控制"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "搜索知识库时的标签过滤"},
            "min_similarity": {"type": "number", "description": "知识库搜索的最小相似度阈值，默认为0.4"},
            "prioritize_recent": {"type": "boolean", "description": "是否优先返回较新的知识，默认为true"},
        },
        "required": ["query"],
    }

    def __init__(self):
        """初始化智能搜索引擎工具"""
        # 冷却时间记录
        self._last_search_times = {}
        # 默认冷却时间(秒)
        self.default_cooldown = 1800  # 30分钟
        # 结果缓存
        self._cache = {}
        # 缓存有效期(秒)
        self.cache_ttl = 3600  # 1小时

    async def execute(self, function_args: Dict[str, Any], message_txt: str = "") -> Dict[str, Any]:
        """执行智能搜索
        
        Args:
            function_args: 工具参数
            message_txt: 原始消息文本
            
        Returns:
            Dict: 工具执行结果
        """
        try:
            with PerformanceTimer("search_engine_execute") as timer:
                # 获取参数
                query = function_args.get("query")
                force_web_search = function_args.get("force_web_search", False)
                time_range = function_args.get("time_range", "month")
                num_results = function_args.get("num_results", 5)
                chat_id = function_args.get("chat_id", "")
                tags = function_args.get("tags", [])
                min_similarity = function_args.get("min_similarity", 0.4)
                prioritize_recent = function_args.get("prioritize_recent", True)
                
                # 获取搜索结果回复模式
                from src.plugins.config.config import global_config
                search_result_mode = getattr(global_config, "search_result_mode", "personalized")
                store_search_results = getattr(global_config, "store_search_results", True)
                
                # 过滤查询中的机器人名称和别名
                bot_nickname = getattr(global_config, "BOT_NICKNAME", None)
                bot_alias_names = getattr(global_config, "BOT_ALIAS_NAMES", [])
                
                original_query = query
                # 构建要过滤的名称列表
                names_to_filter = [name for name in ([bot_nickname] + bot_alias_names) if name]
                # 按长度降序排序，以便先匹配较长的名称
                names_to_filter.sort(key=len, reverse=True)
                
                # 过滤掉查询中的机器人名字和别名
                for name in names_to_filter:
                    # 尝试移除名称后跟逗号或空格的情况
                    query = re.sub(rf'{re.escape(name)}[,，\s]+', '', query, flags=re.IGNORECASE)
                    # 尝试移除单独的名称
                    query = re.sub(rf'^{re.escape(name)}$', '', query, flags=re.IGNORECASE)
                    
                # 去除可能留下的前后空格
                query = query.strip()
                # 如果过滤后查询为空，使用原始查询但移除称呼部分
                if not query:
                    # 尝试仅保留问题部分
                    for name in names_to_filter:
                        if original_query.lower().startswith(name.lower()):
                            query = original_query[len(name):].strip(' ,.，。、?？!！')
                            break
                    # 如果还是空，则使用原始查询
                    if not query:
                        query = original_query
                
                # 记录过滤前后的变化
                if query != original_query:
                    logger.info(f"过滤机器人名称: {original_query} -> {query}")
                
                # 检查缓存
                timer.start_section("check_cache")
                cache_key = f"{query}:{time_range}:{num_results}:{'-'.join(tags)}"
                cache_result = self._check_cache(cache_key)
                if cache_result:
                    logger.info(f"使用缓存结果，查询: {query}")
                    return {
                        "name": self.name, 
                        "content": cache_result.get("content", ""),
                        "from_cache": True,
                        "source": cache_result.get("source", "cache"),
                        "results": cache_result.get("results", [])
                    }
                timer.end_section()
                
                # 检查冷却时间（除非强制搜索）
                if not force_web_search and chat_id:
                    timer.start_section("check_cooldown")
                    cooldown_result = self._check_cooldown(chat_id)
                    if not cooldown_result[0]:  # 冷却中
                        logger.info(f"搜索冷却中，剩余时间:{cooldown_result[1]:.1f}秒")
                        return {
                            "name": self.name, 
                            "content": f"搜索冷却中，剩余{cooldown_result[1]:.1f}秒", 
                            "skipped": True, 
                            "reason": "冷却中"
                        }
                    timer.end_section()
                
                # 1. 先从知识库搜索
                timer.start_section("search_knowledge")
                knowledge_results = []
                from src.plugins.config.config import global_config
                knowledge_base_enable = getattr(global_config, "knowledge_base_enable", True)
                
                if knowledge_base_enable:
                    knowledge_results = await self._search_knowledge(
                        query=query, 
                        tags=tags, 
                        limit=num_results,
                        min_similarity=min_similarity,
                        prioritize_recent=prioritize_recent
                    )
                else:
                    logger.info("知识库查询已禁用，跳过知识库搜索")
                timer.end_section()
                
                # 2. 分析知识库结果质量并决定是否需要网络搜索
                timer.start_section("decide_web_search")
                need_web_search, reason = await self._need_web_search(
                    query=query,
                    knowledge_results=knowledge_results,
                    force_web_search=force_web_search
                )
                timer.end_section()
                
                # 3. 如果需要，执行网络搜索
                web_results = []
                if need_web_search:
                    timer.start_section("web_search")
                    # 更新最后搜索时间
                    if chat_id:
                        self._last_search_times[chat_id] = asyncio.get_event_loop().time()
                    
                    # 获取web_search工具实例并执行搜索
                    from src.do_tool.tool_can_use import get_tool_instance
                    web_search_tool = get_tool_instance("web_search")
                    
                    if web_search_tool:
                        web_search_result = await web_search_tool.execute({
                            "query": query,
                            "num_results": num_results,
                            "time_range": time_range,
                            "force_search": True  # 强制搜索，因为我们已经做了决策
                        })
                        
                        # 在个性化模式下，将网络搜索结果存储到知识库
                        if search_result_mode == "personalized" and store_search_results:
                            if web_search_result and "content" in web_search_result and not web_search_result.get("skipped", False):
                                timer.start_section("store_knowledge")
                                try:
                                    store_knowledge_tool = get_tool_instance("store_knowledge")
                                    if store_knowledge_tool:
                                        await store_knowledge_tool.execute({
                                            "query": query,
                                            "content": web_search_result["content"],
                                            "source": "web_search",
                                            "importance": 3,  # 默认中等重要性
                                            "tags": ["搜索结果", "自动存储", f"搜索时间_{datetime.now().strftime('%Y%m%d')}"]
                                        })
                                        logger.info("搜索结果已保存到知识库")
                                except Exception as e:
                                    logger.error(f"存储搜索结果失败: {e}")
                                timer.end_section()
                        
                        web_results = web_search_result
                    else:
                        logger.error("无法获取web_search工具实例")
                    timer.end_section()
                
                # 4. 整合结果，根据结果模式决定格式
                timer.start_section("combine_results")
                combined_results, content = self._combine_results(
                    query=query,
                    knowledge_results=knowledge_results,
                    web_results=web_results,
                    need_web_search=need_web_search,
                    result_mode=search_result_mode
                )
                timer.end_section()
                
                # 5. 缓存结果
                timer.start_section("cache_results")
                self._cache_results(cache_key, content, combined_results, "combined" if need_web_search else "knowledge")
                # 清理过期缓存
                self._clean_cache()
                timer.end_section()
                
                # 根据搜索结果模式返回不同结构
                if search_result_mode == "direct":
                    # 直接模式：使用表格式结构化输出
                    return {
                        "name": self.name,
                        "content": content,
                        "results": combined_results,
                        "source": "combined" if need_web_search else "knowledge",
                        "web_search_used": need_web_search,
                        "web_search_reason": reason,
                        "result_mode": "direct"
                    }
                else:
                    # 个性化模式：返回适合融入对话中的结果
                    # 确保内容中不包含注释或元数据标记
                    final_content = content
                    # 去除可能的注释和元数据
                    # 匹配任何括号内的注释内容
                    final_content = re.sub(r'\s*[\(（].*?[注註释釋][:：].*?[\)）]', '', final_content)
                    final_content = re.sub(r'\s*[\(（].*?注意.*?[\)）]', '', final_content)
                    # 匹配括号内带关键词的内容
                    final_content = re.sub(r'\s*[\(（].*?整合.*?[\)）]', '', final_content)
                    final_content = re.sub(r'\s*[\(（].*?转化.*?[\)）]', '', final_content)
                    final_content = re.sub(r'\s*[\(（].*?摘自.*?[\)）]', '', final_content)
                    final_content = re.sub(r'\s*[\(（].*?结合.*?[\)）]', '', final_content)
                    final_content = re.sub(r'\s*[\(（].*?知识库.*?[\)）]', '', final_content)
                    final_content = re.sub(r'\s*[\(（].*?来源.*?[\)）]', '', final_content)
                    final_content = re.sub(r'\s*[\(（].*?信息.*?[\)）]', '', final_content)
                    # 去除冗余的空白和断行
                    final_content = re.sub(r'\n{3,}', '\n\n', final_content)
                    final_content = re.sub(r'\s+$', '', final_content)
                    
                    return {
                        "name": self.name,
                        "content": final_content,
                        "results": combined_results,
                        "source": "combined" if need_web_search else "knowledge",
                        "web_search_used": need_web_search,
                        "web_search_reason": reason,
                        "result_mode": "personalized"
                    }
                
        except Exception as e:
            logger.error(f"智能搜索执行失败: {str(e)}")
            return {"name": self.name, "content": f"搜索失败: {str(e)}"}
    
    async def _search_knowledge(self, query: str, tags: List[str] = None, limit: int = 5, 
                               min_similarity: float = 0.4, prioritize_recent: bool = True) -> List[Dict]:
        """从知识库搜索信息
        
        Args:
            query: 搜索查询
            tags: 标签过滤
            limit: 最大返回结果数
            min_similarity: 最小相似度阈值
            prioritize_recent: 是否优先返回较新的内容
            
        Returns:
            List[Dict]: 搜索结果列表
        """
        try:
            from src.do_tool.tool_can_use import get_tool_instance
            search_knowledge_tool = get_tool_instance("search_knowledge")
            
            if search_knowledge_tool:
                results = await search_knowledge_tool.execute({
                    "query": query,
                    "min_similarity": min_similarity,
                    "prioritize_recent": prioritize_recent,
                    "limit": limit
                })
                
                # 处理结果
                if results and isinstance(results, dict) and "results" in results:
                    return results.get("results", [])
                    
            # 尝试使用store_knowledge工具的search_knowledge方法
            store_knowledge_tool = get_tool_instance("store_knowledge")
            if store_knowledge_tool and hasattr(store_knowledge_tool, "search_knowledge"):
                results = await store_knowledge_tool.search_knowledge(
                    query=query,
                    tags=tags,
                    limit=limit,
                    prioritize_recent=prioritize_recent,
                    min_similarity=min_similarity
                )
                return results
                
            logger.warning("无法获取知识搜索工具实例")
            return []
            
        except Exception as e:
            logger.error(f"知识库搜索失败: {str(e)}")
            return []
    
    async def _need_web_search(self, query: str, knowledge_results: List[Dict], force_web_search: bool = False) -> Tuple[bool, str]:
        """判断是否需要执行网络搜索
        
        Args:
            query: 搜索查询
            knowledge_results: 知识库搜索结果
            force_web_search: 是否强制执行网络搜索
            
        Returns:
            Tuple[bool, str]: (是否需要网络搜索, 原因)
        """
        from src.plugins.config.config import global_config
        knowledge_base_enable = getattr(global_config, "knowledge_base_enable", True)
        
        if force_web_search:
            return True, "用户强制要求搜索"
        
        # 如果知识库被禁用，直接进行网络搜索
        if not knowledge_base_enable:
            return True, "知识库查询已禁用"
        
        # 如果没有知识库结果，则需要网络搜索
        if not knowledge_results:
            return True, "知识库中无匹配结果"
        
        # 分析查询是否包含时间敏感词
        time_patterns = [
            r"今天", r"昨天", r"前天", r"明天", r"后天", r"最近", 
            r"这周", r"上周", r"下周", r"这个月", r"上个月", r"今年",
            r"最新", r"刚刚", r"现在", r"现今", r"目前", r"当前",
            r"实时", r"最新动态", r"新闻"
        ]
        
        if any(re.search(pattern, query) for pattern in time_patterns):
            # 检查知识库结果的时间戳
            current_time = time.time()
            newest_result_time = 0
            
            for result in knowledge_results:
                timestamp = result.get("timestamp", 0)
                if timestamp > newest_result_time:
                    newest_result_time = timestamp
            
            # 如果最新结果超过3天，则认为需要刷新
            if current_time - newest_result_time > 259200:  # 3天 = 259200秒
                return True, "知识库信息可能已过时"
        
        # 检查搜索质量
        search_keywords = ["搜索", "查一下", "查一查", "查找", "查询", "搜一下", "搜一搜", 
                           "搜搜看", "查查看", "百度", "谷歌", "搜一搜", "找找看"]
        if any(keyword in query for keyword in search_keywords):
            return True, "用户明确要求搜索"
        
        # 检查知识库结果质量
        if knowledge_results:
            # 如果结果相似度太低，可能需要网络搜索补充
            if knowledge_results[0].get("similarity", 0) < 0.6:
                return True, "知识库匹配度不高，需要补充信息"
                
            # 如果问题是专业性的，检查知识库结果的来源
            professional_patterns = [
                r"技术", r"科技", r"学术", r"研究", r"论文", r"专业", 
                r"领域", r"方法", r"原理", r"机制", r"系统", r"框架"
            ]
            
            if any(re.search(pattern, query) for pattern in professional_patterns):
                # 检查是否有来自可靠来源的知识
                reliable_sources = ["web_search", "education", "academic", "research"]
                has_reliable_source = False
                
                for result in knowledge_results:
                    if result.get("source") in reliable_sources:
                        has_reliable_source = True
                        break
                
                if not has_reliable_source:
                    return True, "专业问题需要更可靠的信息来源"
        
        # 默认情况下，知识库结果足够好，不需要网络搜索
        return False, "知识库结果已满足需求"
    
    def _combine_results(self, query: str, knowledge_results: List[Dict], web_results: Any, need_web_search: bool, result_mode: str = "personalized") -> Tuple[List[Dict], str]:
        """整合知识库和网络搜索结果
        
        Args:
            query: 搜索查询
            knowledge_results: 知识库搜索结果
            web_results: 网络搜索结果
            need_web_search: 是否执行了网络搜索
            result_mode: 结果模式，可选值：personalized（拟人化）、direct（直接输出）
            
        Returns:
            Tuple[List[Dict], str]: (合并后的结果列表, 格式化的内容)
        """
        combined_results = []
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        from src.plugins.config.config import global_config
        
        # 获取配置项
        direct_results_max_length = getattr(global_config, "direct_results_max_length", 1000)
        personalized_format_enabled = getattr(global_config, "personalized_format_enabled", True)
        use_structured_format = getattr(global_config, "use_structured_format", True)
        show_metadata = getattr(global_config, "show_metadata", True)
        max_results_per_source = getattr(global_config, "max_results_per_source", 5)
        
        # 1. 添加知识库结果
        if knowledge_results:
            for i, result in enumerate(knowledge_results):
                combined_results.append({
                    "source": "知识库",
                    "title": f"知识 {i+1}",
                    "content": result.get("content", ""),
                    "url": "",
                    "similarity": result.get("similarity", 0),
                    "time": result.get("timestamp", 0),
                    "tags": result.get("tags", [])
                })
        
        # 2. 如果执行了网络搜索，添加网络结果
        if need_web_search and web_results and isinstance(web_results, dict) and "content" in web_results:
            web_content = web_results.get("content", "")
            
            # 尝试从格式化的内容中提取结果
            web_items = []
            try:
                if "搜索结果" in web_content:
                    # 分析web_content并提取结构化信息
                    result_blocks = re.split(r'📌 结果 \d+:', web_content)
                    
                    for block in result_blocks[1:]:  # 跳过第一个可能是标题部分
                        title_match = re.search(r'📝 标题: (.*?)[\n\r]', block)
                        url_match = re.search(r'🔗 链接: (.*?)[\n\r]', block)
                        date_match = re.search(r'📅 发布日期: (.*?)[\n\r]', block)
                        content_parts = re.split(r'📄 内容:', block)
                        
                        if title_match and len(content_parts) > 1:
                            title = title_match.group(1).strip()
                            url = url_match.group(1).strip() if url_match else ""
                            date = date_match.group(1).strip() if date_match else ""
                            content = content_parts[1].strip()
                            
                            web_items.append({
                                "source": "网络",
                                "title": title,
                                "content": content,
                                "url": url,
                                "date": date
                            })
            except Exception as e:
                logger.error(f"解析网络搜索结果失败: {e}")
            
            # 如果成功提取了结构化信息，添加到合并结果
            if web_items:
                combined_results.extend(web_items)
            else:
                # 否则，添加整个内容作为一个结果
                combined_results.append({
                    "source": "网络",
                    "title": "网络搜索结果",
                    "content": web_content,
                    "url": "",
                })
        
        # 3. 根据模式格式化合并结果
        if result_mode == "direct":
            # 直接模式：结构化输出不经过处理的搜索结果
            if use_structured_format:
                # 使用结构化格式输出
                formatted = f"【搜索结果】查询: {query}\n\n"
                
                # 知识库结果
                knowledge_count = min(len([r for r in combined_results if r.get("source") == "知识库"]), max_results_per_source)
                knowledge_items = [r for r in combined_results if r.get("source") == "知识库"]
                
                if knowledge_items:
                    formatted += f"===== 知识库结果 ({knowledge_count}/{len(knowledge_items)}条) =====\n\n"
                    
                    for i, result in enumerate(knowledge_items[:max_results_per_source]):
                        formatted += f"[{i+1}] {'-'*40}\n"
                        formatted += f"内容: {result.get('content', '')}\n"
                        
                        # 根据配置决定是否展示元数据
                        if show_metadata:
                            formatted += f"{'='*10} 元数据 {'='*10}\n"
                            formatted += f"相似度: {result.get('similarity', 0):.2f}\n"
                            if result.get('tags'):
                                formatted += f"标签: {', '.join(result.get('tags', []))}\n"
                            if result.get('time'):
                                formatted += f"时间: {datetime.fromtimestamp(result.get('time', 0)).strftime('%Y-%m-%d')}\n"
                        formatted += f"{'-'*40}\n\n"
                
                # 网络搜索结果
                web_items = [r for r in combined_results if r.get("source") == "网络"]
                web_count = min(len(web_items), max_results_per_source)
                if web_items:
                    formatted += f"===== 网络搜索结果 ({web_count}/{len(web_items)}条) =====\n\n"
                    
                    for i, result in enumerate(web_items[:max_results_per_source]):
                        formatted += f"[{i+1}] {'-'*40}\n"
                        
                        # 标题和链接
                        if result.get('title'):
                            formatted += f"标题: {result.get('title', '')}\n"
                        if result.get('url'):
                            formatted += f"链接: {result.get('url', '')}\n"
                            
                        # 日期信息（如果有）    
                        if result.get('date') and show_metadata:
                            formatted += f"日期: {result.get('date', '')}\n"
                            
                        # 内容
                        formatted += f"内容: {result.get('content', '')}\n"
                        
                        formatted += f"{'-'*40}\n\n"
                
                # 如果还有更多结果
                if len(knowledge_items) > max_results_per_source or len(web_items) > max_results_per_source:
                    formatted += "...\n"
                    total_more = (len(knowledge_items) - max_results_per_source if len(knowledge_items) > max_results_per_source else 0) + \
                                 (len(web_items) - max_results_per_source if len(web_items) > max_results_per_source else 0)
                    formatted += f"还有 {total_more} 条结果未显示。\n\n"
            else:
                # 使用简单格式输出
                formatted = f"【搜索结果】查询: {query}\n\n"
                
                # 结果计数
                total_results = len(combined_results)
                formatted += f"共找到 {total_results} 条相关结果。\n\n"
                
                # 展示所有合并结果
                for i, result in enumerate(combined_results[:max_results_per_source*2]):
                    source = result.get("source", "未知")
                    title = result.get("title", "")
                    content = result.get("content", "")
                    
                    # 限制内容长度
                    if len(content) > 300:
                        content = content[:297] + "..."
                    
                    formatted += f"{i+1}. [{source}] {title}\n"
                    formatted += f"{content}\n\n"
                
                # 如果还有更多结果
                if len(combined_results) > max_results_per_source*2:
                    formatted += f"还有 {len(combined_results) - max_results_per_source*2} 条结果未显示。\n"
            
            # 如果没有任何结果
            if not combined_results:
                formatted += "没有找到相关信息。"
                
        else:
            # 个性化模式：生成易于集成到对话中的结果
            # 首先提取最相关的内容
            relevant_content = ""
            
            # 从知识库和网络搜索结果中提取最相关内容
            if combined_results:
                # 按相似度或其他相关性指标排序
                sorted_results = sorted(
                    combined_results, 
                    key=lambda x: x.get("similarity", 0) if x.get("source") == "知识库" else 0.5,
                    reverse=True
                )
                
                # 获取前3个最相关结果
                top_results = sorted_results[:3]
                
                # 合并内容并清理任何可能的注释
                content_pieces = []
                for result in top_results:
                    content = result.get("content", "").strip()
                    
                    # 清理所有注释格式的内容
                    content = re.sub(r'\s*[\(（].*?[注註释釋][:：].*?[\)）]', '', content)
                    content = re.sub(r'\s*[\(（].*?注意.*?[\)）]', '', content)
                    content = re.sub(r'\s*[\(（].*?整合.*?[\)）]', '', content)
                    content = re.sub(r'\s*[\(（].*?转化.*?[\)）]', '', content)
                    content = re.sub(r'\s*[\(（].*?摘自.*?[\)）]', '', content)
                    content = re.sub(r'\s*[\(（].*?结合.*?[\)）]', '', content)
                    content = re.sub(r'\s*[\(（].*?知识库.*?[\)）]', '', content)
                    content = re.sub(r'\s*[\(（].*?来源.*?[\)）]', '', content)
                    content = re.sub(r'\s*[\(（].*?信息.*?[\)）]', '', content)
                    # 去除冗余的空白和断行
                    content = re.sub(r'\n{3,}', '\n\n', content)
                    content = re.sub(r'\s+$', '', content)
                    
                    if content:
                        # 对专业性内容进行转换，使其更加自然和对话化
                        # 1. 将过于正式的表述替换为更加日常化的表述
                        content = re.sub(r'据报道', '好像', content)
                        content = re.sub(r'根据.*?调查', '最近', content)
                        content = re.sub(r'研究表明', '好像', content)
                        content = re.sub(r'专家认为', '有人说', content)
                        
                        # 2. 删除过多的详细数据，保留核心信息
                        content = re.sub(r'\d+\.\d+%', '不少', content)
                        
                        # 3. 将长句子拆分成更短的句子
                        if len(content) > 100:
                            sentences = re.split(r'[。！？.!?]', content)
                            content = '. '.join([s for s in sentences if s.strip()][:2])
                            
                        content_pieces.append(content)
                
                # 合并到最终结果
                if content_pieces:
                    # 构建更自然的回复
                    if len(content_pieces) == 1:
                        relevant_content = content_pieces[0]
                    else:
                        # 使用更自然的连接词
                        connectors = ["", "另外，", "还有，", "我还了解到，", "顺便一提，"]
                        connected_content = ""
                        
                        for i, piece in enumerate(content_pieces):
                            if i == 0:
                                connected_content = piece
                            else:
                                connected_content += f" {connectors[min(i, len(connectors)-1)]}{piece}"
                        
                        relevant_content = connected_content
                    
                    # 限制总长度并确保结尾完整
                    if len(relevant_content) > 150:
                        # 找到最后一个句号的位置
                        last_period = max(relevant_content[:150].rfind('。'), 
                                         relevant_content[:150].rfind('.'), 
                                         relevant_content[:150].rfind('!'), 
                                         relevant_content[:150].rfind('！'))
                        
                        if last_period > 50:  # 确保至少有足够的内容
                            relevant_content = relevant_content[:last_period+1]
                        else:
                            relevant_content = relevant_content[:147] + "..."
            
            # 添加人性化的表达
            if not relevant_content:
                # 没有找到相关内容的情况
                no_result_responses = [
                    "抱歉，我没有找到关于这个问题的相关信息呢。",
                    "对不起，我找不到这个问题的答案，要不换个话题聊聊？",
                    "嗯...我好像没有找到相关的信息，可以换个问题问我吗？",
                    "我查了一下，没有找到相关的资料呢，要不我们聊点别的？"
                ]
                import random
                formatted = random.choice(no_result_responses)
            else:
                # 找到相关内容的情况
                if personalized_format_enabled:
                    # 如果是信息性回复，加入适当的引导词
                    if any(keyword in query for keyword in ["什么", "如何", "怎么", "为什么", "多少", "哪里", "是谁"]):
                        starters = [
                            "",
                            "我了解到，",
                            "关于这个问题，",
                            "根据我所知，",
                            "我找到的信息是，"
                        ]
                        import random
                        formatted = f"{random.choice(starters)}{relevant_content}"
                    elif any(keyword in query for keyword in ["最新", "新闻", "最近", "进展", "消息"]):
                        # 对于新闻类查询，使用更新闻化的语气
                        starters = [
                            "",
                            "最近，",
                            "我看到，",
                            "最新消息是，",
                            "听说"
                        ]
                        import random
                        formatted = f"{random.choice(starters)}{relevant_content}"
                    else:
                        # 对于一般问题，直接给出内容
                        formatted = relevant_content
                        
                    # 检查是否有更多结果未显示，使用更自然的表述
                    if len(combined_results) > 3:
                        # 根据情境选择不同的结尾
                        if "?" in query or "？" in query:
                            # 问题类查询
                            formatted += "\n\n这些是我找到的主要信息，希望能帮到你~"
                        elif any(keyword in query for keyword in ["最新", "新闻", "最近"]):
                            # 新闻类查询
                            formatted += "\n\n这是我了解到的最新情况~"
                        else:
                            # 一般查询
                            formatted += "\n\n以上是相关信息，如果你想了解更多细节，可以再问我哦~"
                else:
                    # 不启用拟人化格式，只返回内容
                    formatted = relevant_content
        
        return combined_results, formatted
    
    def _check_cache(self, cache_key: str) -> Dict:
        """检查缓存
        
        Args:
            cache_key: 缓存键
            
        Returns:
            Dict: 缓存结果，没有则返回None
        """
        current_time = asyncio.get_event_loop().time()
        if cache_key in self._cache:
            cache_time, cache_data = self._cache[cache_key]
            # 检查缓存是否仍然有效
            if current_time - cache_time < self.cache_ttl:
                return cache_data
        return None
    
    def _cache_results(self, cache_key: str, content: str, results: List[Dict], source: str):
        """缓存搜索结果
        
        Args:
            cache_key: 缓存键
            content: 格式化的内容
            results: 结果列表
            source: 结果来源
        """
        current_time = asyncio.get_event_loop().time()
        self._cache[cache_key] = (current_time, {
            "content": content,
            "results": results,
            "source": source
        })
    
    def _clean_cache(self):
        """清理过期缓存"""
        current_time = asyncio.get_event_loop().time()
        expired_keys = []
        
        for key, (cache_time, _) in self._cache.items():
            if current_time - cache_time > self.cache_ttl:
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


# 测试代码
if __name__ == "__main__":
    async def test_search_engine():
        """测试智能搜索引擎工具"""
        try:
            print("开始测试智能搜索引擎工具...")
            search_engine = SearchEngineTool()
            
            # 测试查询
            test_query = "人工智能最新发展"
            print(f"测试查询: {test_query}")
            
            # 执行搜索
            result = await search_engine.execute({
                "query": test_query,
                "chat_id": "test_chat",
                "force_web_search": True
            })
            
            # 打印结果
            print("\n搜索结果:")
            if result and "content" in result:
                print(result["content"])
            else:
                print("搜索失败或无结果")
                print(result)
            
            print("\n测试完成")
            
        except Exception as e:
            print(f"测试过程中出错: {str(e)}")
            import traceback
            traceback.print_exc()
    
    # 运行测试
    asyncio.run(test_search_engine()) 