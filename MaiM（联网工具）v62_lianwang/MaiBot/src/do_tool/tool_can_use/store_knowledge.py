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

logger = get_module_logger("store_knowledge_tool")


class StoreKnowledgeTool(BaseTool):
    """将知识存储到数据库的工具"""

    name = "store_knowledge"
    description = "将搜索结果、用户输入或总结等信息存储到知识库中，支持标签分类、重要度标记、知识验证和知识图谱"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "原始查询内容"},
            "content": {"type": "string", "description": "要存储的知识内容"},
            "source": {"type": "string", "description": "知识来源，如web_search、user_input、summary等"},
            "timestamp": {"type": "number", "description": "时间戳"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "知识标签，用于分类"},
            "importance": {"type": "integer", "description": "重要程度，1-5，数字越大表示越重要"},
            "related_to": {"type": "string", "description": "关联的其他知识ID"},
            "override_similar": {"type": "boolean", "description": "是否覆盖相似内容，默认为false"},
            "verify_facts": {"type": "boolean", "description": "是否验证知识中的事实，默认为true"},
            "extract_entities": {"type": "boolean", "description": "是否提取实体和关系用于知识图谱，默认为true"},
            "ttl": {"type": "number", "description": "知识生存时间（TTL），单位秒，None表示永不过期"}
        },
        "required": ["query", "content"],
    }

    async def execute(self, function_args: Dict[str, Any], message_txt: str = "") -> Dict[str, Any]:
        """将知识存储到数据库

        Args:
            function_args: 工具参数
            message_txt: 原始消息文本

        Returns:
            Dict: 工具执行结果
        """
        try:
            # 获取基本参数
            query = function_args.get("query")
            content = function_args.get("content")
            source = function_args.get("source", "user_input")
            timestamp = function_args.get("timestamp", datetime.now().timestamp())
            
            # 获取增强参数
            tags = function_args.get("tags", [])
            importance = function_args.get("importance")
            related_to = function_args.get("related_to", "")
            override_similar = function_args.get("override_similar", False)
            ttl = function_args.get("ttl", None)  # 添加TTL参数
            
            # 知识验证和知识图谱参数
            verify_facts = function_args.get("verify_facts", True)
            extract_entities = function_args.get("extract_entities", True)
            
            # 验证参数
            if not content or content.strip() == "":
                return {"name": self.name, "content": "无法存储空内容"}
            
            # 验证重要程度参数
            if importance is not None:
                try:
                    importance = int(importance)  # 确保是整数
                    if importance < 1 or importance > 5:
                        logger.warning(f"重要程度超出范围 (1-5)，提供的值: {importance}，已设置为默认值 3")
                        importance = 3
                except (ValueError, TypeError):
                    logger.warning(f"重要程度必须是整数，提供的值: {importance}，已设置为默认值 3")
                    importance = 3
            else:
                # 增强：根据内容自动评估重要性
                importance = await self._evaluate_importance(content, query, source)
            
            # 增强：如果没有提供标签，自动生成标签
            if not tags:
                tags = await self._generate_tags(content, query)
                logger.info(f"自动生成标签: {tags}")
            
            # 获取内容的嵌入向量
            embedding = await get_embedding(content, request_type="info_storage")
            if not embedding:
                logger.error("无法获取内容的嵌入向量")
                return {"name": self.name, "content": "无法获取内容的嵌入向量，存储失败"}
            
            # 知识验证（如果启用）
            verification_result = None
            if verify_facts:
                verification_result = await self._verify_facts(content)
                # 如果验证为假，根据置信度决定是否仍然存储
                if verification_result and verification_result.get("is_factual") is False:
                    confidence = verification_result.get("confidence", 0)
                    if confidence > 0.8:  # 高置信度的错误信息
                        logger.warning(f"内容验证失败，不进行存储: {content[:50]}...")
                        return {
                            "name": self.name, 
                            "content": f"知识验证失败，内容可能包含错误信息: {verification_result.get('reason', '未知原因')}",
                            "verification": verification_result
                        }
            
            # 实体和关系提取（如果启用）
            entities_and_relations = None
            if extract_entities:
                entities_and_relations = await self._extract_entities_and_relations(content)
                # 如果成功提取到实体，自动添加为标签
                if entities_and_relations and entities_and_relations.get("entities"):
                    extracted_tags = [entity.lower() for entity in entities_and_relations.get("entities")]
                    # 合并标签并去重
                    tags = list(set(tags + extracted_tags))
            
            # 增强：自动计算TTL
            if ttl is None:
                ttl = self._calculate_ttl(importance, source)
                logger.info(f"自动计算TTL: {ttl} 秒")
            
            # 检查是否已存在相似内容
            similar_content = await self._check_similar_content(embedding, content)
            
            if similar_content:
                # 处理相似内容
                if override_similar:
                    # 更新现有内容而不是插入新内容
                    existing_id = similar_content.get("_id")
                    update_data = {
                        "$set": {
                            "content": content,
                            "embedding": embedding,
                            "updated_at": datetime.fromtimestamp(timestamp),
                            "last_query": query,
                            "source": source,
                            "importance": importance,
                            "ttl": ttl,  # 更新TTL
                        }
                    }
                    
                    # 添加验证结果（如果有）
                    if verification_result:
                        update_data["$set"]["verification"] = verification_result
                    
                    # 添加实体和关系（如果有）
                    if entities_and_relations:
                        update_data["$set"]["entities"] = entities_and_relations.get("entities", [])
                        update_data["$set"]["relations"] = entities_and_relations.get("relations", [])
                    
                    # 追加标签而不是覆盖
                    if tags:
                        update_data["$addToSet"] = {"tags": {"$each": tags}}
                    
                    # 更新相关联的知识
                    if related_to:
                        if "$addToSet" not in update_data:
                            update_data["$addToSet"] = {}
                        update_data["$addToSet"]["related_to"] = related_to
                        
                        # 双向关联 - 在关联知识中也添加本知识的引用
                        self._update_reverse_relation(related_to, str(existing_id))
                    
                    db.knowledges.update_one({"_id": existing_id}, update_data)
                    
                    # 更新知识图谱
                    if entities_and_relations and entities_and_relations.get("relations"):
                        await self._update_knowledge_graph(str(existing_id), entities_and_relations.get("relations"))
                    
                    logger.info(f"已更新现有知识: ID={existing_id}, 内容={content[:50]}...")
                    return {
                        "name": self.name, 
                        "content": f"已更新现有知识（相似度: {similar_content.get('similarity', 0):.2f}）",
                        "verification": verification_result,
                        "entities": entities_and_relations.get("entities") if entities_and_relations else None
                    }
                else:
                    logger.info(f"已存在相似内容，跳过存储: {content[:50]}...")
                    return {
                        "name": self.name, 
                        "content": f"已存在相似内容（相似度: {similar_content.get('similarity', 0):.2f}），跳过存储"
                    }
            
            # 存储新知识到数据库
            knowledge = {
                "content": content,
                "embedding": embedding,
                "query": query,
                "source": source,
                "created_at": datetime.fromtimestamp(timestamp),
                "updated_at": datetime.fromtimestamp(timestamp),
                "timestamp": timestamp,  # 确保有timestamp字段
                "importance": importance,
                "access_count": 0,
                "tags": tags,
                "related_to": [related_to] if related_to else [],
                "ttl": ttl,  # 添加TTL
            }
            
            # 添加验证结果（如果有）
            if verification_result:
                knowledge["verification"] = verification_result
            
            # 添加实体和关系（如果有）
            if entities_and_relations:
                knowledge["entities"] = entities_and_relations.get("entities", [])
                knowledge["relations"] = entities_and_relations.get("relations", [])
            
            result = db.knowledges.insert_one(knowledge)
            knowledge_id = str(result.inserted_id)
            
            # 如果有关联知识，更新双向关联
            if related_to:
                self._update_reverse_relation(related_to, knowledge_id)
            
            # 更新知识图谱
            if entities_and_relations and entities_and_relations.get("relations"):
                await self._update_knowledge_graph(knowledge_id, entities_and_relations.get("relations"))
            
            # 定期检查索引 - 改为每24小时执行一次
            self._check_indexes_periodically()
            
            logger.info(f"成功存储知识: ID={knowledge_id}, 内容={content[:50]}...")
            
            response = {
                "name": self.name, 
                "content": f"知识已成功存储到数据库，ID: {knowledge_id}",
                "knowledge_id": knowledge_id,
                "tags": tags,
                "importance": importance,
                "ttl": ttl,
                "verification": verification_result,
                "entities": entities_and_relations.get("entities") if entities_and_relations else None
            }
            
            return response
        except Exception as e:
            logger.error(f"存储知识失败: {str(e)}")
            return {"name": self.name, "content": f"存储知识失败: {str(e)}"}
    
    @log_async_performance
    async def search_knowledge(self, query: str, tags: List[str] = None, limit: int = 5, 
                         prioritize_recent: bool = True, min_similarity: float = 0.35, 
                         ttl_check: bool = True, time_start: Optional[float] = None,
                         time_end: Optional[float] = None) -> List[Dict]:
        """搜索知识库中的内容
        
        Args:
            query: 搜索查询
            tags: 标签过滤
            limit: 最大返回结果数
            prioritize_recent: 是否优先返回较新的内容
            min_similarity: 最小相似度阈值
            ttl_check: 是否检查TTL有效期
            time_start: 开始时间戳
            time_end: 结束时间戳
            
        Returns:
            List[Dict]: 搜索结果列表
        """
        try:
            # 检查缓存中是否有结果
            cache_key = f"knowledge_search:{query}:{'-'.join(tags) if tags else ''}:{limit}:{prioritize_recent}:{min_similarity}:{ttl_check}:{time_start}:{time_end}"
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                logger.info(f"使用缓存的知识库搜索结果: {query[:20]}")
                return cached_result
                
            with PerformanceTimer(f"search_knowledge-{query[:20]}") as timer:
                # 添加诊断计数器
                start_docs = db.knowledges.count_documents({})
                logger.debug(f"知识库搜索开始 - 文档总数: {start_docs}")
                
                # 0. 提取关键词和扩展查询
                timer.start_section("expand_query")
                expanded_query = query
                try:
                    # 尝试进行查询扩展
                    keywords = re.findall(r'\w+', query.lower())
                    if keywords and len(keywords) <= 5:  # 只对短查询进行扩展
                        expanded_terms = []
                        for keyword in keywords:
                            if len(keyword) >= 3:  # 只扩展有意义的词
                                # 添加同义词或相关词 (简化实现)
                                expanded_terms.append(keyword)
                        
                        if expanded_terms:
                            expanded_query = f"{query} {' '.join(expanded_terms)}"
                            logger.debug(f"查询扩展: {query} -> {expanded_query}")
                except Exception as e:
                    logger.debug(f"查询扩展失败: {e}")
                    expanded_query = query  # 失败时使用原始查询
                timer.end_section()
            
                # 1. 获取查询的嵌入向量
                timer.start_section("get_embedding")
                query_embedding = await get_embedding(expanded_query, request_type="info_retrieval")
                timer.end_section()
                
                if not query_embedding:
                    logger.error("无法获取查询的嵌入向量")
                    return []
            
                # 2. 构建查询条件
                timer.start_section("build_query")
                match_condition = {}
                if tags:
                    match_condition["tags"] = {"$in": tags}
                    
                    # 记录标签过滤后的文档数量
                    tag_filtered_docs = db.knowledges.count_documents({"tags": {"$in": tags}})
                    logger.debug(f"标签过滤后文档数: {tag_filtered_docs}")
            
                # 3. 添加时间范围条件
                current_time = time.time()
                if time_start is not None and time_end is not None:
                    # 确保时间戳在合理范围内
                    if time_start > current_time + 86400 * 365:  # 如果开始时间超过一年后
                        time_start = current_time - 86400  # 默认为一天前
                    if time_end > current_time + 86400 * 365:  # 如果结束时间超过一年后
                        time_end = current_time + 86400  # 默认为一天后
                    
                    match_condition["timestamp"] = {
                        "$gte": time_start,
                        "$lte": time_end
                    }
                                        
                    # 记录时间过滤后的文档数量
                    time_filtered_docs = db.knowledges.count_documents({
                        "timestamp": {"$gte": time_start, "$lte": time_end}
                    })
                    logger.debug(f"时间过滤后文档数: {time_filtered_docs}")
            
                # 4. 添加TTL检查
                if ttl_check:
                    ttl_condition = {
                        "$or": [
                            {"ttl": None},  # 永不过期的知识
                            {"ttl": {"$exists": False}},  # 没有TTL字段的知识
                            {
                                "$expr": {
                                    "$gt": [
                                        {"$add": ["$timestamp", {"$ifNull": ["$ttl", 0]}]},
                                        current_time
                                    ]
                                }
                            }  # timestamp + ttl > current_time，即TTL未过期
                        ]
                    }
                        
                    # 合并TTL条件
                    if match_condition:
                        match_condition = {"$and": [match_condition, ttl_condition]}
                    else:
                        match_condition = ttl_condition
                timer.end_section()
                
                # 记录查询条件命中的文档数
                if match_condition:
                    filtered_docs = db.knowledges.count_documents(match_condition)
                    logger.debug(f"匹配条件过滤后文档数: {filtered_docs}")
                
                # 5. 执行相似度搜索 - 优化查询逻辑
                timer.start_section("vector_search")
                
                # 优化: 如果过滤后的文档少于50个，使用简化的流程
                results = []
                if filtered_docs < 50:
                    # 先获取符合条件的文档
                    docs = list(db.knowledges.find(
                        match_condition,
                        {
                            "_id": 1, "content": 1, "query": 1, "source": 1, 
                            "created_at": 1, "updated_at": 1, "timestamp": 1,
                            "importance": 1, "tags": 1, "embedding": 1, "access_count": 1
                        }
                    ))
                    
                    # 在Python中计算相似度
                    for doc in docs:
                        if "embedding" in doc and doc["embedding"]:
                            similarity = self._calculate_cosine_similarity(query_embedding, doc["embedding"])
                            if similarity >= min_similarity:
                                doc["similarity"] = similarity
                                # 计算组合分数
                                if prioritize_recent and "timestamp" in doc:
                                    recency_score = 1 / (1 + (current_time - doc.get("timestamp", 0)) / 86400)
                                    doc["combined_score"] = similarity * 0.7 + recency_score * 0.3
                                else:
                                    doc["combined_score"] = similarity
                                results.append(doc)
                    
                    # 排序和限制结果数量
                    results.sort(key=lambda x: x["combined_score"], reverse=True)
                    results = results[:limit]
                else:
                    # 使用MongoDB聚合管道
                    pipeline = [
                        {"$match": match_condition},
                        {
                            "$addFields": {
                                "dotProduct": {
                                    "$reduce": {
                                        "input": {"$zip": {"inputs": [query_embedding, "$embedding"]}},
                                        "initialValue": 0,
                                        "in": {
                                            "$add": [
                                                "$$value", 
                                                {
                                                    "$multiply": [
                                                        {
                                                            "$convert": {
                                                                "input": "$$this.0", 
                                                                "to": "double", 
                                                                "onError": 0.0, 
                                                                "onNull": 0.0
                                                            }
                                                        }, 
                                                        {
                                                            "$convert": {
                                                                "input": "$$this.1", 
                                                                "to": "double", 
                                                                "onError": 0.0, 
                                                                "onNull": 0.0
                                                            }
                                                        }
                                                    ]
                                                }
                                            ]
                                        }
                                    }
                                }
                            }
                        },
                        {
                            "$addFields": {
                                "magnitude1": {
                                    "$sqrt": {
                                        "$reduce": {
                                            "input": query_embedding,
                                            "initialValue": 0,
                                            "in": {"$add": ["$$value", {"$multiply": ["$$this", "$$this"]}]}
                                        }
                                    }
                                },
                                "magnitude2": {
                                    "$sqrt": {
                                        "$reduce": {
                                            "input": "$embedding",
                                            "initialValue": 0,
                                            "in": {"$add": ["$$value", {"$multiply": ["$$this", "$$this"]}]}
                                        }
                                    }
                                }
                            }
                        },
                        {
                            "$addFields": {
                                "similarity": {
                                    "$cond": {
                                        "if": {"$eq": [{"$multiply": ["$magnitude1", "$magnitude2"]}, 0]},
                                        "then": 0,
                                        "else": {"$divide": ["$dotProduct", {"$multiply": ["$magnitude1", "$magnitude2"]}]}
                                    }
                                }
                            }
                        },
                        {"$match": {"similarity": {"$gte": min_similarity}}},
                        {"$sort": {"similarity": -1}},
                    ]
                
                    # 如果需要优先考虑最近的内容，添加复合排序
                    if prioritize_recent:
                        pipeline.append({
                            "$addFields": {
                                "recency_score": {
                                    "$divide": [
                                        1, 
                                        {"$add": [
                                            1, 
                                            {"$divide": [
                                                {"$subtract": [current_time, {"$ifNull": ["$timestamp", 0]}]}, 
                                                86400
                                            ]}
                                        ]}
                                    ]
                                },
                                "combined_score": {
                                    "$add": [
                                        {"$multiply": ["$similarity", 0.7]},
                                        {"$multiply": [
                                            {"$divide": [
                                                1, 
                                                {"$add": [
                                                    1, 
                                                    {"$divide": [
                                                        {"$subtract": [current_time, {"$ifNull": ["$timestamp", 0]}]}, 
                                                        86400
                                                    ]}
                                                ]}
                                            ]}, 
                                            0.3
                                        ]}
                                    ]
                                }
                            }
                        })
                        pipeline.append({"$sort": {"combined_score": -1}})
                
                    # 执行聚合查询
                    results = list(db.knowledges.aggregate(pipeline))
                timer.end_section()
                
                # 6. 更新访问计数
                timer.start_section("update_access_count")
                for result in results:
                    try:
                        db.knowledges.update_one(
                            {"_id": result["_id"]},
                            {"$inc": {"access_count": 1}}
                        )
                    except Exception as e:
                        logger.error(f"更新访问计数时出错: {str(e)}")
                timer.end_section()
                
                # 7. 缓存结果
                self._store_in_cache(cache_key, results)
                
                return results
                
        except Exception as e:
            logger.error(f"搜索知识库时出错: {str(e)}")
            return []
    
    async def _check_similar_content(self, embedding: list, content: str, threshold: float = 0.92) -> Optional[Dict]:
        """检查是否存在相似内容
        
        Args:
            embedding: 内容的嵌入向量
            content: 内容文本
            threshold: 相似度阈值
        
        Returns:
            Optional[Dict]: 相似内容信息，如果不存在则返回None
        """
        try:
            # 内容缓存键 - 使用内容的哈希
            import hashlib
            content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            cache_key = f"similar_content:{content_hash}"
            
            # 尝试从缓存中获取结果
            cache_result = self._get_from_cache(cache_key)
            if cache_result is not None:
                logger.info(f"使用缓存的相似内容检查结果")
                return cache_result
            
            try:
                # 异步执行相似度检查，带超时
                result = await asyncio.wait_for(
                    self._async_check_similar_content(embedding, content, threshold),
                    timeout=10.0  # 10秒超时
                )
                
                # 缓存结果（无论是否找到相似内容）
                self._store_in_cache(cache_key, result, ttl=86400)  # 缓存1天
                
                return result
            except asyncio.TimeoutError:
                logger.warning(f"相似内容检查超时，跳过详细检查")
                return None
                
        except Exception as e:
            logger.error(f"检查相似内容时出错: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def _async_check_similar_content(self, embedding: list, content: str, threshold: float = 0.92) -> Optional[Dict]:
        """异步检查相似内容，支持高效查询
        
        Args:
            embedding: 内容的嵌入向量
            content: 内容文本
            threshold: 相似度阈值
            
        Returns:
            Optional[Dict]: 相似内容信息
        """
        with PerformanceTimer("check_similar_content") as timer:
            timer.start_section("optimize_query")
            
            # 优化1: 使用简单的字符串匹配进行预过滤
            # 提取内容的关键词（简化方法，实际应使用更好的分词）
            words = set(re.sub(r'[^\w\s]', '', content).split())
            significant_words = [w for w in words if len(w) > 3]  # 只使用长度>3的词
            
            # 如果有显著词，使用文本匹配预过滤
            prefilter_query = {}
            if len(significant_words) >= 2:
                # 选择最多5个关键词用于查询
                keywords = significant_words[:5] if len(significant_words) > 5 else significant_words
                word_query = []
                for word in keywords:
                    word_query.append({"content": {"$regex": word, "$options": "i"}})
                
                if word_query:
                    prefilter_query = {"$or": word_query}
            
            # 优化2: 限制查询的文档数量
            timer.end_section()
            
            # 执行预过滤查询
            timer.start_section("prefilter_query")
            candidate_docs = []
            max_candidates = 100  # 最多处理100个候选
            
            if prefilter_query:
                # 有预过滤条件时使用
                candidate_docs = list(db.knowledges.find(
                    prefilter_query,
                    {"_id": 1, "content": 1, "embedding": 1, "tags": 1, "importance": 1}
                ).limit(max_candidates))
                
                logger.debug(f"预过滤匹配到 {len(candidate_docs)} 个候选文档")
            else:
                # 没有预过滤条件时，默认取最近添加的文档
                candidate_docs = list(db.knowledges.find(
                    {},
                    {"_id": 1, "content": 1, "embedding": 1, "tags": 1, "importance": 1}
                ).sort("_id", -1).limit(max_candidates))
            timer.end_section()
            
            # 如果候选集很少，直接进行Python内存中的相似度计算
            timer.start_section("similarity_calculation")
            if len(candidate_docs) <= max_candidates:
                # 在Python中计算相似度
                max_similarity = 0
                most_similar_doc = None
                
                for doc in candidate_docs:
                    if "embedding" in doc and doc["embedding"]:
                        similarity = self._calculate_cosine_similarity(embedding, doc["embedding"])
                        if similarity >= threshold and similarity > max_similarity:
                            max_similarity = similarity
                            most_similar_doc = doc
                
                if most_similar_doc:
                    most_similar_doc["similarity"] = max_similarity
                    timer.end_section()
                    return most_similar_doc
            else:
                # 修复: 使用更稳健的MongoDB聚合管道，避免类型转换错误
                try:
                    # 创建安全的聚合流水线
                    pipeline = [
                        # 限制为预过滤的文档ID
                        {"$match": {"_id": {"$in": [doc["_id"] for doc in candidate_docs]}}},
                        # 手动计算相似性，而不使用可能存在类型转换问题的$convert
                        {
                            "$project": {
                                "_id": 1,
                                "content": 1,
                                "tags": 1,
                                "importance": 1,
                                "similarity": {
                                    "$let": {
                                        "vars": {
                                            "dotProduct": {"$sum": {"$map": {
                                                "input": {"$range": [0, {"$size": "$embedding"}]},
                                                "as": "i",
                                                "in": {"$multiply": [
                                                    {"$arrayElemAt": [embedding, "$$i"]},
                                                    {"$arrayElemAt": ["$embedding", "$$i"]}
                                                ]}
                                            }}},
                                            "mag1": {"$sqrt": {"$sum": {"$map": {
                                                "input": {"$range": [0, {"$size": "$embedding"}]},
                                                "as": "i",
                                                "in": {"$pow": [{"$arrayElemAt": [embedding, "$$i"]}, 2]}
                                            }}}},
                                            "mag2": {"$sqrt": {"$sum": {"$map": {
                                                "input": {"$range": [0, {"$size": "$embedding"}]},
                                                "as": "i",
                                                "in": {"$pow": [{"$arrayElemAt": ["$embedding", "$$i"]}, 2]}
                                            }}}}
                                        },
                                        "in": {"$cond": {
                                            "if": {"$or": [
                                                {"$eq": ["$$mag1", 0]},
                                                {"$eq": ["$$mag2", 0]}
                                            ]},
                                            "then": 0,
                                            "else": {"$divide": ["$$dotProduct", {"$multiply": ["$$mag1", "$$mag2"]}]}
                                        }}
                                    }
                                }
                            }
                        },
                        {"$match": {"similarity": {"$gte": threshold}}},
                        {"$sort": {"similarity": -1}},
                        {"$limit": 1}
                    ]
                    
                    # 执行查询
                    results = list(db.knowledges.aggregate(pipeline))
                    timer.end_section()
                    
                    return results[0] if results else None
                except Exception as e:
                    # 如果聚合管道出错，回退到Python内存中计算
                    logger.error(f"MongoDB聚合管道执行出错，回退到Python计算: {str(e)}")
                    # 在Python中计算相似度
                    max_similarity = 0
                    most_similar_doc = None
                    
                    for doc in candidate_docs:
                        if "embedding" in doc and doc["embedding"]:
                            similarity = self._calculate_cosine_similarity(embedding, doc["embedding"])
                            if similarity >= threshold and similarity > max_similarity:
                                max_similarity = similarity
                                most_similar_doc = doc
                    
                    if most_similar_doc:
                        most_similar_doc["similarity"] = max_similarity
                        return most_similar_doc
            
            timer.end_section()
            return None
    
    def _get_from_cache(self, key: str) -> Any:
        """从缓存中获取值"""
        try:
            # 实现简单的内存缓存
            if not hasattr(self, '_cache'):
                self._cache = {}
                self._cache_times = {}
            
            if key in self._cache:
                cache_time = self._cache_times.get(key, 0)
                # 检查是否过期 (默认1天)
                if time.time() - cache_time < 86400:
                    return self._cache[key]
                
                # 过期清理
                del self._cache[key]
                del self._cache_times[key]
                
            return None
        except Exception as e:
            logger.warning(f"从缓存获取数据失败: {e}")
            return None
    
    def _store_in_cache(self, key: str, value: Any, ttl: int = 86400) -> None:
        """存储值到缓存"""
        try:
            if not hasattr(self, '_cache'):
                self._cache = {}
                self._cache_times = {}
            
            self._cache[key] = value
            self._cache_times[key] = time.time()
            
            # 如果缓存过大，清理最旧的条目
            max_cache_size = 1000
            if len(self._cache) > max_cache_size:
                oldest_keys = sorted(self._cache_times.keys(), key=lambda k: self._cache_times[k])
                for old_key in oldest_keys[:100]:  # 清理100个最旧的条目
                    del self._cache[old_key]
                    del self._cache_times[old_key]
        except Exception as e:
            logger.warning(f"存储缓存数据失败: {e}")
    
    def _calculate_cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算两个向量的余弦相似度
        
        Args:
            vec1: 第一个向量
            vec2: 第二个向量
            
        Returns:
            float: 余弦相似度
        """
        try:
            if len(vec1) != len(vec2):
                logger.error(f"向量长度不匹配: {len(vec1)} != {len(vec2)}")
                return 0.0
                
            # 计算点积
            dot_product = sum(x * y for x, y in zip(vec1, vec2))
            
            # 计算向量的模
            magnitude1 = math.sqrt(sum(x * x for x in vec1))
            magnitude2 = math.sqrt(sum(x * x for x in vec2))
            
            # 避免除以零
            if magnitude1 == 0 or magnitude2 == 0:
                return 0.0
                
            # 计算余弦相似度
            similarity = dot_product / (magnitude1 * magnitude2)
            
            # 确保相似度在 [-1, 1] 范围内
            return max(-1.0, min(1.0, similarity))
            
        except Exception as e:
            logger.error(f"计算余弦相似度时出错: {str(e)}")
            return 0.0
    
    def _ensure_indexes(self):
        """确保必要的数据库索引存在"""
        try:
            # 检查索引是否存在
            existing_indexes = db.knowledges.index_information()
            
            # 创建索引，如果不存在
            if "importance_1" not in existing_indexes:
                db.knowledges.create_index("importance")
                logger.info("已创建重要程度索引")
            
            if "tags_1" not in existing_indexes:
                db.knowledges.create_index("tags")
                logger.info("已创建标签索引")
                
            if "created_at_1" not in existing_indexes:
                db.knowledges.create_index("created_at")
                logger.info("已创建创建时间索引")
            
            if "access_count_1" not in existing_indexes:
                db.knowledges.create_index("access_count")
                logger.info("已创建访问计数索引")
                
            # 为嵌入向量添加索引，加速向量搜索
            if "embedding_1" not in existing_indexes:
                db.knowledges.create_index([("embedding", 1)], sparse=True)
                logger.info("已创建嵌入向量索引")
            
            # 添加时间戳索引，优化TTL查询
            if "timestamp_1" not in existing_indexes:
                db.knowledges.create_index("timestamp")
                logger.info("已创建时间戳索引")
                
            # 新增索引 - 实体索引
            if "entities_1" not in existing_indexes:
                db.knowledges.create_index("entities")
                logger.info("已创建实体索引")
                
            # 确保知识图谱集合的索引
            if "knowledge_graph" not in db.list_collection_names():
                db.create_collection("knowledge_graph")
                db.knowledge_graph.create_index([("subject", 1), ("predicate", 1), ("object", 1)], unique=True)
                db.knowledge_graph.create_index("subject")
                db.knowledge_graph.create_index("object")
                logger.info("已创建知识图谱集合和索引")
        except Exception as e:
            logger.error(f"创建索引时出错: {str(e)}")
    
    def _update_reverse_relation(self, knowledge_id: str, related_id: str):
        """更新反向关联关系
        
        Args:
            knowledge_id: 知识ID
            related_id: 关联的知识ID
        """
        try:
            if not knowledge_id or not related_id:
                return
            
            # 检查知识ID格式
            if not isinstance(knowledge_id, str) or not isinstance(related_id, str):
                logger.warning(f"知识ID格式错误: {knowledge_id}, {related_id}")
                return
                
            db.knowledges.update_one(
                {"_id": knowledge_id},
                {"$addToSet": {"related_to": related_id}}
            )
            logger.info(f"已更新反向关联: {knowledge_id} -> {related_id}")
        except Exception as e:
            logger.error(f"更新反向关联时出错: {str(e)}")
    
    async def _verify_facts(self, content: str) -> Dict[str, Any]:
        """验证内容中的事实性（简单实现）
        
        Args:
            content: 要验证的内容
            
        Returns:
            Dict: 验证结果，包含是否事实、置信度和原因
        """
        try:
            # 调用外部事实验证API或模型（简化实现）
            # 实际应用中，可以使用现有的事实验证服务或自建模型
            
            # 简单实现：使用关键词检测明显的错误信息
            # 在实际应用中应替换为真正的事实验证API
            warning_patterns = [
                r'地球是平的',
                r'疫苗导致自闭症',
                r'5G传播病毒',
                r'(人类从未登上|登月是骗局)',
                r'气候变化是骗局'
            ]
            
            for pattern in warning_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    return {
                        "is_factual": False,
                        "confidence": 0.9,
                        "reason": f"内容包含可能的错误信息: 匹配模式 '{pattern}'",
                        "verified_at": datetime.now()
                    }
            
            # 在这里，应该调用更复杂的事实验证API
            # 例如: response = await call_fact_verification_api(content)
            
            # 简化实现
            return {
                "is_factual": True,
                "confidence": 0.8,
                "reason": "初步验证通过",
                "verified_at": datetime.now()
            }
        except Exception as e:
            logger.error(f"事实验证时出错: {str(e)}")
            return {
                "is_factual": True,  # 默认通过
                "confidence": 0.5,
                "reason": f"验证过程出错: {str(e)}",
                "verified_at": datetime.now()
            }
    
    async def _extract_entities_and_relations(self, text: str) -> Dict[str, Any]:
        """从文本中提取实体和关系
        
        Args:
            text: 输入文本
            
        Returns:
            Dict[str, Any]: 包含实体和关系的字典
        """
        try:
            # 使用正则表达式提取实体和关系
            entities = re.findall(r'[A-Za-z0-9\u4e00-\u9fa5]+', text)
            relations = []
            
            # 提取简单的主谓宾关系（简化实现）
            # 在实际应用中，应该使用更复杂的NLP工具
            sentences = re.split(r'[.!?。！？]', text)
            for sentence in sentences:
                if len(sentence.strip()) > 0:
                    # 简单规则：尝试找出主谓宾
                    words = sentence.strip().split()
                    if len(words) >= 3:
                        # 构建简单关系
                        relation = {
                            "subject": words[0],
                            "predicate": words[1] if len(words) > 1 else "",
                            "object": words[2] if len(words) > 2 else ""
                        }
                        relations.append(relation)
            
            # 去重
            entities = list(set(entities))
            
            return {
                "entities": entities,
                "relations": relations
            }
            
        except Exception as e:
            logger.error(f"提取实体和关系时出错: {str(e)}")
            return {"entities": [], "relations": []}
    
    async def _update_knowledge_graph(self, knowledge_id: str, relations: List[Dict]):
        """更新知识图谱
        
        Args:
            knowledge_id: 知识ID
            relations: 关系列表，每个关系包含subject、predicate和object
        """
        try:
            if not relations:
                return
                
            # 批量插入关系到知识图谱集合
            for relation in relations:
                subject = relation.get("subject")
                predicate = relation.get("predicate")
                object = relation.get("object")
                
                if not subject or not predicate or not object:
                    continue
                
                # 构建图谱节点
                graph_relation = {
                    "subject": subject,
                    "predicate": predicate,
                    "object": object,
                    "source_knowledge_id": knowledge_id,
                    "created_at": datetime.now()
                }
                
                # 使用upsert避免重复
                db.knowledge_graph.update_one(
                    {
                        "subject": subject,
                        "predicate": predicate,
                        "object": object
                    },
                    {"$set": graph_relation},
                    upsert=True
                )
            
            logger.info(f"成功为知识ID {knowledge_id} 更新了 {len(relations)} 个关系到知识图谱")
        except Exception as e:
            logger.error(f"更新知识图谱时出错: {str(e)}")
    
    async def search_knowledge_graph(self, entity: str, relation_type: str = None, limit: int = 10) -> List[Dict]:
        """搜索知识图谱中的关系
        
        Args:
            entity: 要搜索的实体
            relation_type: 关系类型（可选）
            limit: 最大返回结果数
            
        Returns:
            List[Dict]: 关系列表
        """
        try:
            # 构建查询条件
            query = {
                "$or": [
                    {"subject": entity},
                    {"object": entity}
                ]
            }
            
            if relation_type:
                query["predicate"] = relation_type
            
            # 执行查询
            results = list(db.knowledge_graph.find(query).limit(limit))
            
            # 格式化结果，添加人类可读的描述
            formatted_results = []
            for result in results:
                if result["subject"] == entity:
                    description = f"{entity} {result['predicate']} {result['object']}"
                else:
                    description = f"{result['subject']} {result['predicate']} {entity}"
                
                formatted_result = {
                    "relation_id": str(result["_id"]),
                    "description": description,
                    "subject": result["subject"],
                    "predicate": result["predicate"],
                    "object": result["object"],
                    "source_knowledge_id": result.get("source_knowledge_id")
                }
                
                formatted_results.append(formatted_result)
            
            return formatted_results
        except Exception as e:
            logger.error(f"搜索知识图谱时出错: {str(e)}")
            return []

    async def _evaluate_importance(self, content: str, query: str, source: str) -> int:
        """评估知识的重要性

        Args:
            content: 知识内容
            query: 原始查询
            source: 知识来源

        Returns:
            int: 重要性评分（1-5）
        """
        try:
            # 基础重要性分数（中等）
            base_importance = 3
            
            # 1. 基于内容长度的评分调整
            content_length = len(content)
            if content_length > 500:  # 长内容可能更重要
                base_importance += 1
            elif content_length < 50:  # 短内容可能不太重要
                base_importance -= 1
            
            # 2. 基于来源的评分调整
            if source == "web_search":  # 搜索结果可能更重要
                base_importance += 1
            elif source == "auto_generated":  # 自动生成内容可能不太重要
                base_importance -= 1
            
            # 3. 关键词加权
            important_keywords = [
                "重要", "关键", "核心", "必须", "最新", "突破",
                "官方", "权威", "专家", "研究", "发现", "宣布",
                "紧急", "警告", "必知", "critical", "important",
                "essential", "key", "vital", "crucial"
            ]
            
            for keyword in important_keywords:
                if keyword in content or keyword in query:
                    base_importance += 1
                    break  # 只加一次
            
            # 4. 时间相关性加权
            time_keywords = [
                "今天", "昨天", "本周", "本月", "最近", "新", 
                "刚刚", "现在", "当前", "today", "yesterday",
                "this week", "this month", "recent", "new", 
                "just now", "current"
            ]
            
            for keyword in time_keywords:
                if keyword in content or keyword in query:
                    base_importance += 1
                    break  # 只加一次
            
            # 确保最终分数在1-5之间
            final_importance = max(1, min(5, base_importance))
            
            return final_importance
        except Exception as e:
            logger.error(f"评估知识重要性时出错: {str(e)}")
            return 3  # 默认中等重要性
    
    async def _generate_tags(self, content: str, query: str) -> List[str]:
        """为知识内容生成标签

        Args:
            content: 知识内容
            query: 原始查询

        Returns:
            List[str]: 生成的标签列表
        """
        try:
            tags = []
            
            # 1. 从原始查询中提取关键词作为标签
            query_words = re.findall(r'[\w\u4e00-\u9fff]{2,}', query)
            for word in query_words:
                if len(word) >= 2 and word.lower() not in ['什么', '怎么', '如何', '为什么', 'the', 'and', 'for', 'are', 'with']:
                    tags.append(word.lower())
            
            # 2. 从内容中提取关键词
            # 简单实现：提取中英文词汇
            content_words = re.findall(r'[\w\u4e00-\u9fff]{2,}', content)
            word_freq = {}
            
            for word in content_words:
                word = word.lower()
                if word not in ['什么', '怎么', '如何', '为什么', 'the', 'and', 'for', 'are', 'with']:
                    word_freq[word] = word_freq.get(word, 0) + 1
            
            # 选择频率最高的几个词作为标签
            sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
            for word, freq in sorted_words[:5]:  # 最多添加5个高频词
                if word not in tags and len(word) >= 2:
                    tags.append(word)
            
            # 3. 添加来源标签
            if "web_search" in query.lower() or "搜索" in query:
                tags.append("网络搜索")
            
            # 4. 添加预定义类别标签
            categories = {
                "技术": ["编程", "代码", "软件", "开发", "技术", "算法", "数据", "程序", "python", "java", "计算机"],
                "科学": ["科学", "物理", "化学", "生物", "天文", "医学", "研究", "实验"],
                "历史": ["历史", "古代", "朝代", "文明", "年代", "历史事件"],
                "文化": ["文化", "艺术", "音乐", "电影", "文学", "书籍", "作品"],
                "地理": ["地理", "国家", "城市", "地区", "位置", "地点"],
                "人物": ["人物", "名人", "人", "谁"]
            }
            
            content_lower = content.lower()
            query_lower = query.lower()
            
            for category, keywords in categories.items():
                if any(keyword in content_lower or keyword in query_lower for keyword in keywords):
                    tags.append(category)
                    break
            
            # 去重
            tags = list(set(tags))
            
            # 限制标签数量
            return tags[:10]  # 最多返回10个标签
        except Exception as e:
            logger.error(f"生成标签时出错: {str(e)}")
            return []
    
    def _calculate_ttl(self, importance: float, source: str) -> int:
        """计算知识项的生存时间(TTL)

        Args:
            importance: 重要性分数
            source: 知识来源

        Returns:
            int: TTL值(秒)
        """
        try:
            # 基础TTL
            base_ttl = 3600  # 1小时
            
            # 根据重要性调整
            importance_factor = 1.0 + importance
            
            # 根据来源调整
            source_factor = 1.0
            if source == "web_search":
                source_factor = 1.5  # 搜索结果保留更长时间
            elif source == "user_input":
                source_factor = 2.0  # 用户输入保留更长时间
            elif source == "auto_generated":
                source_factor = 0.5  # 自动生成的内容保留更短时间
            
            # 计算最终TTL
            ttl = int(base_ttl * importance_factor * source_factor)
            
            return ttl
            
        except Exception as e:
            logger.error(f"计算TTL时出错: {str(e)}")
            return 3600  # 默认1小时

    def _check_indexes_periodically(self):
        """定期检查索引，每24小时执行一次"""
        try:
            current_time = time.time()
            
            # 使用类变量存储上次索引检查时间
            if not hasattr(StoreKnowledgeTool, '_last_index_check'):
                StoreKnowledgeTool._last_index_check = 0
            
            # 只有当距离上次检查超过24小时时才执行索引检查
            if current_time - StoreKnowledgeTool._last_index_check > 86400:  # 86400秒 = 24小时
                logger.info("执行定期索引检查（24小时一次）")
                self._ensure_indexes()
                StoreKnowledgeTool._last_index_check = current_time
                
        except Exception as e:
            logger.error(f"定期检查索引时出错: {str(e)}")


# 注册工具
register_tool(StoreKnowledgeTool) 