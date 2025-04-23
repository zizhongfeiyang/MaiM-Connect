from src.do_tool.tool_can_use.base_tool import BaseTool, register_tool
from src.do_tool.tool_can_use.store_knowledge import StoreKnowledgeTool
from src.common.database import db
from src.common.logger import get_module_logger
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
import time
import json
import re
import networkx as nx
from bson.objectid import ObjectId
import asyncio

logger = get_module_logger("knowledge_manager_tool")

class KnowledgeManagerTool(BaseTool):
    """知识库管理工具，负责知识库的维护、优化和统计"""

    name = "knowledge_manager"
    description = "管理知识库，包括合并相似知识、删除过时知识、优化知识图谱、生成知识报告"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string", 
                "description": "要执行的操作，支持：cleanup(清理知识)、merge(合并知识)、report(生成报告)、optimize(优化知识库)、verify(验证知识)、start_maintenance(启动定期维护)",
                "enum": ["cleanup", "merge", "report", "optimize", "verify", "start_maintenance"]
            },
            "days": {
                "type": "integer", 
                "description": "操作涉及的时间范围(天)，例如清理7天前的知识",
                "default": 30
            },
            "limit": {
                "type": "integer", 
                "description": "操作涉及的知识数量限制",
                "default": 100
            },
            "similarity_threshold": {
                "type": "number", 
                "description": "相似度阈值，用于合并或查找相似知识",
                "default": 0.85
            },
            "knowledge_ids": {
                "type": "array", 
                "items": {"type": "string"}, 
                "description": "操作涉及的知识ID列表"
            },
            "tags": {
                "type": "array", 
                "items": {"type": "string"}, 
                "description": "按标签筛选知识"
            }
        },
        "required": ["action"],
    }

    def __init__(self):
        """初始化知识库管理工具"""
        # 维护线程引用
        self.maintenance_thread = None
        self.maintenance_running = False
        
        # 在工具初始化时自动启动维护任务
        asyncio.create_task(self._auto_start_maintenance())

    async def _auto_start_maintenance(self):
        """自动启动维护任务"""
        try:
            logger.info("知识库管理工具初始化中，准备启动维护任务...")
            # 延迟几秒，确保系统其他部分已初始化
            await asyncio.sleep(5)
            await self._start_maintenance_task()
            logger.info("知识库管理工具自动启动维护任务成功")
        except Exception as e:
            logger.error(f"自动启动知识库维护任务失败: {str(e)}")

    async def execute(self, function_args: Dict[str, Any], message_txt: str = "") -> Dict[str, Any]:
        """执行知识库管理操作

        Args:
            function_args: 工具参数
            message_txt: 原始消息文本

        Returns:
            Dict: 工具执行结果
        """
        try:
            # 获取操作类型
            action = function_args.get("action")
            
            # 获取其他参数
            days = function_args.get("days", 30)
            limit = function_args.get("limit", 100)
            similarity_threshold = function_args.get("similarity_threshold", 0.85)
            knowledge_ids = function_args.get("knowledge_ids", [])
            tags = function_args.get("tags", [])
            
            # 根据操作类型执行不同的功能
            if action == "cleanup":
                result = await self._cleanup_knowledge(days, limit, tags)
                return {"name": self.name, "content": result}
            
            elif action == "merge":
                result = await self._merge_similar_knowledge(similarity_threshold, limit, knowledge_ids, tags)
                return {"name": self.name, "content": result}
            
            elif action == "report":
                result = await self._generate_knowledge_report(days)
                return {"name": self.name, "content": result}
            
            elif action == "optimize":
                result = await self._optimize_knowledge_base(limit, tags)
                return {"name": self.name, "content": result}
            
            elif action == "verify":
                result = await self._verify_knowledge(limit, knowledge_ids, tags)
                return {"name": self.name, "content": result}
            
            elif action == "start_maintenance":
                # 启动定期维护
                result = await self._start_maintenance_task()
                return {"name": self.name, "content": result, "success": True}
            
            else:
                return {"name": self.name, "content": f"不支持的操作: {action}"}
                
        except Exception as e:
            logger.error(f"知识库管理操作失败: {str(e)}")
            return {"name": self.name, "content": f"知识库管理操作失败: {str(e)}"}
    
    async def _cleanup_knowledge(self, days: int = 30, limit: int = 100, tags: List[str] = None) -> str:
        """清理过时或低价值的知识
        
        Args:
            days: 清理多少天前的知识
            limit: 最多清理多少条知识
            tags: 按标签筛选知识
            
        Returns:
            str: 清理结果描述
        """
        try:
            # 计算时间阈值
            time_threshold = datetime.now() - timedelta(days=days)
            timestamp_threshold = time_threshold.timestamp()
            
            # 构建查询条件
            query = {
                "created_at": {"$lt": timestamp_threshold},
                "importance": {"$lt": 4}  # 只清理重要性小于4的知识
            }
            
            # 添加标签过滤
            if tags:
                query["tags"] = {"$in": tags}
            
            # 查找符合条件的知识
            candidates = list(db.knowledges.find(
                query,
                {"_id": 1, "content": 1, "importance": 1, "access_count": 1, "created_at": 1}
            ).sort([("importance", 1), ("access_count", 1)]).limit(limit))
            
            if not candidates:
                return f"没有找到符合条件的过时知识（{days}天前，重要性<4）"
            
            # 计算要删除的知识
            to_delete = []
            for knowledge in candidates:
                # 根据重要性和访问次数计算"保留分数"
                importance = knowledge.get("importance", 1)
                access_count = knowledge.get("access_count", 0)
                
                # 保留分数计算：重要性(1-3) + 访问次数(0+)/10 = 0.0-4.0分
                retention_score = importance + min(access_count / 10, 1.0)
                
                # 分数低于2.5的知识将被删除
                if retention_score < 2.5:
                    to_delete.append(knowledge["_id"])
            
            # 执行删除
            if to_delete:
                result = db.knowledges.delete_many({"_id": {"$in": to_delete}})
                deleted_count = result.deleted_count
                
                logger.info(f"已清理 {deleted_count} 条过时知识")
                return f"已清理 {deleted_count} 条过时知识（{days}天前，重要性<4，低访问量）"
            else:
                return f"没有符合清理条件的知识（所有候选知识的保留分数都>=2.5）"
            
        except Exception as e:
            logger.error(f"清理知识时出错: {str(e)}")
            return f"清理知识时出错: {str(e)}"
    
    async def _merge_similar_knowledge(self, similarity_threshold: float = 0.85, 
                               limit: int = 50, 
                               knowledge_ids: List[str] = None,
                               tags: List[str] = None) -> str:
        """合并相似的知识条目
        
        Args:
            similarity_threshold: 相似度阈值
            limit: 处理的知识数量限制
            knowledge_ids: 指定的知识ID列表
            tags: 按标签筛选知识
            
        Returns:
            str: 合并结果描述
        """
        try:
            # 查询条件
            query = {}
            
            # 如果指定了知识ID
            if knowledge_ids and len(knowledge_ids):
                object_ids = [ObjectId(kid) for kid in knowledge_ids if ObjectId.is_valid(kid)]
                query["_id"] = {"$in": object_ids}
            
            # 添加标签过滤
            if tags:
                query["tags"] = {"$in": tags}
            
            # 获取知识条目
            knowledge_entries = list(db.knowledges.find(
                query,
                {"_id": 1, "content": 1, "embedding": 1, "tags": 1, "importance": 1, "created_at": 1, "updated_at": 1}
            ).limit(limit))
            
            if not knowledge_entries:
                return "没有找到符合条件的知识条目"
            
            # 构建相似度图，用于聚类
            G = nx.Graph()
            
            # 添加所有节点
            for entry in knowledge_entries:
                G.add_node(str(entry["_id"]), data=entry)
            
            # 计算相似度并添加边
            for i in range(len(knowledge_entries)):
                for j in range(i+1, len(knowledge_entries)):
                    entry1 = knowledge_entries[i]
                    entry2 = knowledge_entries[j]
                    
                    # 计算余弦相似度
                    similarity = self._calculate_cosine_similarity(
                        entry1.get("embedding", []),
                        entry2.get("embedding", [])
                    )
                    
                    # 如果相似度大于阈值，添加边
                    if similarity >= similarity_threshold:
                        G.add_edge(str(entry1["_id"]), str(entry2["_id"]), weight=similarity)
            
            # 查找连通分量（相似知识组）
            connected_components = list(nx.connected_components(G))
            
            # 记录待合并的组
            merge_groups = []
            for component in connected_components:
                if len(component) >= 2:  # 只处理至少有2个节点的组
                    entries = [G.nodes[node_id]["data"] for node_id in component]
                    merge_groups.append(entries)
            
            if not merge_groups:
                return f"未找到需要合并的相似知识组 (阈值: {similarity_threshold})"
            
            # 执行合并
            merged_count = 0
            for group in merge_groups:
                # 按重要性和最后更新时间排序
                sorted_group = sorted(
                    group, 
                    key=lambda x: (x.get("importance", 1), x.get("updated_at", x.get("created_at", 0))),
                    reverse=True
                )
                
                # 选择最重要/最新的条目作为主条目
                main_entry = sorted_group[0]
                main_id = main_entry["_id"]
                
                # 收集要合并的ID
                merge_ids = [entry["_id"] for entry in sorted_group[1:]]
                
                if merge_ids:
                    # 合并标签
                    all_tags = set(main_entry.get("tags", []))
                    for entry in sorted_group[1:]:
                        all_tags.update(entry.get("tags", []))
                    
                    # 更新主条目
                    db.knowledges.update_one(
                        {"_id": main_id},
                        {
                            "$set": {
                                "tags": list(all_tags),
                                "merged_count": len(merge_ids),
                                "merged_at": datetime.now(),
                                "importance": max(main_entry.get("importance", 1), 3)  # 提升重要性
                            }
                        }
                    )
                    
                    # 删除其他条目
                    db.knowledges.delete_many({"_id": {"$in": merge_ids}})
                    
                    merged_count += len(merge_ids)
                    logger.info(f"已合并知识组: 主条目ID={main_id}, 合并{len(merge_ids)}条")
            
            return f"已合并 {len(merge_groups)} 组相似知识，共删除 {merged_count} 条冗余条目"
            
        except Exception as e:
            logger.error(f"合并知识时出错: {str(e)}")
            return f"合并知识时出错: {str(e)}"
    
    def _calculate_cosine_similarity(self, vec1, vec2):
        """计算两个向量的余弦相似度"""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        
        try:
            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            magnitude1 = sum(a * a for a in vec1) ** 0.5
            magnitude2 = sum(b * b for b in vec2) ** 0.5
            
            if magnitude1 == 0 or magnitude2 == 0:
                return 0.0
                
            return dot_product / (magnitude1 * magnitude2)
        except Exception as e:
            logger.error(f"计算相似度时出错: {str(e)}")
            return 0.0
    
    async def _generate_knowledge_report(self, days: int = 30) -> str:
        """生成知识库统计报告
        
        Args:
            days: 报告涵盖的时间范围(天)
            
        Returns:
            str: 统计报告
        """
        try:
            # 计算时间阈值
            time_threshold = datetime.now() - timedelta(days=days)
            timestamp_threshold = time_threshold.timestamp()
            
            # 总知识数量
            total_count = db.knowledges.count_documents({})
            if total_count == 0:
                return "知识库为空，无法生成报告"
            
            # 最近新增的知识数量
            recent_count = db.knowledges.count_documents({"timestamp": {"$gte": timestamp_threshold}})
            
            # 按重要性统计
            importance_stats = {}
            for i in range(1, 6):
                importance_stats[i] = db.knowledges.count_documents({"importance": i})
            
            # 按来源统计
            source_stats = {}
            for source_doc in db.knowledges.aggregate([
                {"$group": {"_id": "$source", "count": {"$sum": 1}}}
            ]):
                source = source_doc["_id"] or "unknown"
                source_stats[source] = source_doc["count"]
            
            # 按标签统计Top10
            tag_stats = {}
            for tag_doc in db.knowledges.aggregate([
                {"$unwind": "$tags"},
                {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 10}
            ]):
                tag_stats[tag_doc["_id"]] = tag_doc["count"]
            
            # 访问最多的知识Top5
            top_accessed = []
            for doc in db.knowledges.find(
                {}, 
                {"_id": 1, "content": 1, "access_count": 1, "tags": 1}
            ).sort("access_count", -1).limit(5):
                top_accessed.append({
                    "id": str(doc["_id"]),
                    "content": doc["content"][:100] + "..." if len(doc["content"]) > 100 else doc["content"],
                    "access_count": doc.get("access_count", 0),
                    "tags": doc.get("tags", [])
                })
            
            # 最近添加的知识Top5
            recently_added = []
            for doc in db.knowledges.find(
                {}, 
                {"_id": 1, "content": 1, "timestamp": 1, "tags": 1}
            ).sort("timestamp", -1).limit(5):
                created_time = datetime.fromtimestamp(doc.get("timestamp", 0))
                recently_added.append({
                    "id": str(doc["_id"]),
                    "content": doc["content"][:100] + "..." if len(doc["content"]) > 100 else doc["content"],
                    "created_at": created_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "tags": doc.get("tags", [])
                })
            
            # 构建报告文本
            report = f"知识库统计报告 (最近{days}天)\n"
            report += f"===================================\n\n"
            
            report += f"总知识数量: {total_count}\n"
            report += f"最近{days}天新增: {recent_count}\n\n"
            
            report += "按重要性分布:\n"
            for i in range(1, 6):
                report += f"  {i}星: {importance_stats.get(i, 0)}条 ({importance_stats.get(i, 0)/total_count*100:.1f}%)\n"
            report += "\n"
            
            report += "按来源分布:\n"
            for source, count in source_stats.items():
                report += f"  {source}: {count}条 ({count/total_count*100:.1f}%)\n"
            report += "\n"
            
            report += "热门标签Top10:\n"
            for tag, count in tag_stats.items():
                report += f"  {tag}: {count}条\n"
            report += "\n"
            
            report += "访问最多的知识Top5:\n"
            for i, item in enumerate(top_accessed, 1):
                report += f"  {i}. [{item['access_count']}次] {item['content']}\n"
                report += f"     标签: {', '.join(item['tags'])}\n"
            report += "\n"
            
            report += "最近添加的知识Top5:\n"
            for i, item in enumerate(recently_added, 1):
                report += f"  {i}. [{item['created_at']}] {item['content']}\n"
                report += f"     标签: {', '.join(item['tags'])}\n"
            
            return report
            
        except Exception as e:
            logger.error(f"生成知识报告时出错: {str(e)}")
            return f"生成知识报告时出错: {str(e)}"
    
    async def _optimize_knowledge_base(self, limit: int = 100, tags: List[str] = None) -> str:
        """优化知识库，包括标签优化、知识关联等
        
        Args:
            limit: 处理的知识数量限制
            tags: 按标签筛选知识
            
        Returns:
            str: 优化结果描述
        """
        try:
            # 查询条件
            query = {}
            
            # 添加标签过滤
            if tags:
                query["tags"] = {"$in": tags}
            
            # 1. 查找缺少标签的知识
            no_tags_query = {}
            if query:
                no_tags_query.update(query)
            no_tags_query.update({
                "$or": [
                    {"tags": {"$exists": False}},
                    {"tags": []},
                    {"tags": None}
                ]
            })
            
            no_tags_entries = list(db.knowledges.find(
                no_tags_query,
                {"_id": 1, "content": 1, "query": 1}
            ).limit(limit))
            
            # 为缺少标签的知识添加标签
            tags_added = 0
            if no_tags_entries:
                store_knowledge_tool = StoreKnowledgeTool()
                
                for entry in no_tags_entries:
                    content = entry.get("content", "")
                    query = entry.get("query", "")
                    
                    # 生成标签
                    generated_tags = await store_knowledge_tool._generate_tags(content, query)
                    
                    if generated_tags:
                        # 更新知识条目
                        db.knowledges.update_one(
                            {"_id": entry["_id"]},
                            {"$set": {"tags": generated_tags}}
                        )
                        tags_added += 1
            
            # 2. 查找缺少重要性评分的知识
            no_importance_query = {}
            if query:
                no_importance_query.update(query)
            no_importance_query.update({
                "$or": [
                    {"importance": {"$exists": False}},
                    {"importance": None}
                ]
            })
            
            no_importance_entries = list(db.knowledges.find(
                no_importance_query,
                {"_id": 1, "content": 1, "query": 1, "source": 1}
            ).limit(limit))
            
            # 为缺少重要性的知识评估重要性
            importance_added = 0
            if no_importance_entries:
                store_knowledge_tool = StoreKnowledgeTool()
                
                for entry in no_importance_entries:
                    content = entry.get("content", "")
                    query = entry.get("query", "")
                    source = entry.get("source", "unknown")
                    
                    # 评估重要性
                    importance = await store_knowledge_tool._evaluate_importance(content, query, source)
                    
                    # 更新知识条目
                    db.knowledges.update_one(
                        {"_id": entry["_id"]},
                        {"$set": {"importance": importance}}
                    )
                    importance_added += 1
            
            # 3. 查找缺少TTL的知识
            no_ttl_query = {}
            if query:
                no_ttl_query.update(query)
            no_ttl_query.update({
                "$or": [
                    {"ttl": {"$exists": False}},
                    {"ttl": None}
                ]
            })
            
            no_ttl_entries = list(db.knowledges.find(
                no_ttl_query,
                {"_id": 1, "importance": 1, "source": 1}
            ).limit(limit))
            
            # 为缺少TTL的知识设置TTL
            ttl_added = 0
            if no_ttl_entries:
                store_knowledge_tool = StoreKnowledgeTool()
                
                for entry in no_ttl_entries:
                    importance = entry.get("importance", 3)
                    source = entry.get("source", "unknown")
                    
                    # 计算TTL
                    ttl = store_knowledge_tool._calculate_ttl(importance, source)
                    
                    # 更新知识条目
                    db.knowledges.update_one(
                        {"_id": entry["_id"]},
                        {"$set": {"ttl": ttl}}
                    )
                    ttl_added += 1
            
            # 4. 标签规范化 - 合并相似标签
            tag_mapping = {
                "编程": ["program", "programming", "code", "coding"],
                "python": ["py", "python3", "python2"],
                "技术": ["technology", "tech"],
                "ai": ["人工智能", "artificial intelligence"],
                "机器学习": ["ml", "machine learning"],
                "深度学习": ["dl", "deep learning"]
            }
            
            tag_normalized = 0
            for standard_tag, similar_tags in tag_mapping.items():
                # 查找包含相似标签的知识，但不包含标准标签
                for similar_tag in similar_tags:
                    # 逐个处理相似标签，避免冲突
                    query = {
                        "$and": [
                            {"tags": similar_tag},
                            {"tags": {"$ne": standard_tag}}  # 确保不包含标准标签
                        ]
                    }
                    
                    # 更新：添加标准标签
                    update_result = db.knowledges.update_many(
                        query,
                        {"$addToSet": {"tags": standard_tag}}
                    )
                    tag_normalized += update_result.modified_count
                    
                    # 移除相似标签
                    if update_result.modified_count > 0:
                        db.knowledges.update_many(
                            {"tags": {"$all": [standard_tag, similar_tag]}},
                            {"$pull": {"tags": similar_tag}}
                        )
            
            # 返回优化报告
            report = "知识库优化完成\n"
            report += "===================================\n\n"
            report += f"为 {tags_added} 条知识添加了标签\n"
            report += f"为 {importance_added} 条知识评估了重要性\n"
            report += f"为 {ttl_added} 条知识设置了TTL\n"
            report += f"规范化了 {tag_normalized} 条知识的标签\n"
            
            return report
            
        except Exception as e:
            logger.error(f"优化知识库时出错: {str(e)}")
            return f"优化知识库时出错: {str(e)}"
    
    async def _verify_knowledge(self, limit: int = 50, 
                        knowledge_ids: List[str] = None,
                        tags: List[str] = None) -> str:
        """验证知识的准确性
        
        Args:
            limit: 处理的知识数量限制
            knowledge_ids: 指定的知识ID列表
            tags: 按标签筛选知识
            
        Returns:
            str: 验证结果描述
        """
        try:
            # 查询条件
            query = {}
            
            # 如果指定了知识ID
            if knowledge_ids and len(knowledge_ids):
                object_ids = [ObjectId(kid) for kid in knowledge_ids if ObjectId.is_valid(kid)]
                query["_id"] = {"$in": object_ids}
            
            # 添加标签过滤
            if tags:
                query["tags"] = {"$in": tags}
            
            # 添加验证过滤 - 优先验证未验证过的
            query.update({
                "$or": [
                    {"verification": {"$exists": False}},
                    {"verification": None}
                ]
            })
            
            # 获取知识条目
            knowledge_entries = list(db.knowledges.find(
                query,
                {"_id": 1, "content": 1, "source": 1, "importance": 1}
            ).sort("importance", -1).limit(limit))
            
            if not knowledge_entries:
                return "没有找到需要验证的知识条目"
            
            # 验证知识
            store_knowledge_tool = StoreKnowledgeTool()
            verified_count = 0
            factual_count = 0
            non_factual_count = 0
            
            for entry in knowledge_entries:
                content = entry.get("content", "")
                
                # 验证知识
                verification_result = await store_knowledge_tool._verify_facts(content)
                
                if verification_result:
                    # 更新知识条目
                    db.knowledges.update_one(
                        {"_id": entry["_id"]},
                        {"$set": {"verification": verification_result}}
                    )
                    verified_count += 1
                    
                    if verification_result.get("is_factual", True):
                        factual_count += 1
                    else:
                        non_factual_count += 1
            
            return f"已验证 {verified_count} 条知识，其中 {factual_count} 条被判定为事实，{non_factual_count} 条被判定含有错误"
            
        except Exception as e:
            logger.error(f"验证知识时出错: {str(e)}")
            return f"验证知识时出错: {str(e)}"

    async def _start_maintenance_task(self) -> str:
        """启动定期维护任务
        
        Returns:
            str: 启动结果描述
        """
        # 如果已有维护线程在运行，不重复启动
        if self.maintenance_thread and self.maintenance_thread.is_alive():
            return "知识库维护任务已在运行中"
            
        import threading
        import asyncio
        
        # 设置线程运行标志
        self.maintenance_running = True
        
        # 定义知识库维护循环
        async def maintain_knowledge_database():
            """定期维护知识库"""
            logger.info("知识库维护循环已启动")
            
            while self.maintenance_running:
                try:
                    # 1. 优化知识库 - 每小时运行一次
                    logger.info("执行知识库例行优化...")
                    optimize_result = await self._optimize_knowledge_base(limit=200)
                    logger.info(f"知识库优化完成: {optimize_result}")
                    
                    # 2. 清理过时知识 - 每天清理一次
                    # 只在每天的0-1点之间运行清理
                    current_hour = datetime.now().hour
                    if 0 <= current_hour <= 1:
                        logger.info("执行知识库过期内容清理...")
                        cleanup_result = await self._cleanup_knowledge(days=30, limit=100)
                        logger.info(f"过时知识清理完成: {cleanup_result}")
                    
                    # 3. 合并相似知识 - 每周运行一次
                    # 只在周末运行合并操作
                    if datetime.now().weekday() >= 5:  # 5=周六，6=周日
                        logger.info("执行知识库相似内容合并...")
                        merge_result = await self._merge_similar_knowledge(similarity_threshold=0.88, limit=100)
                        logger.info(f"相似知识合并完成: {merge_result}")
                    
                    # 4. 生成知识库报告 - 每周日
                    if datetime.now().weekday() == 6:  # 周日
                        logger.info("生成知识库状态报告...")
                        report = await self._generate_knowledge_report(days=30)
                        logger.info(f"知识库报告生成完成: \n{report}")
                        
                except Exception as e:
                    logger.error(f"知识库维护任务执行失败: {str(e)}")
                
                # 等待1小时
                await asyncio.sleep(3600)
        
        # 创建线程运行函数
        def run_maintenance_thread():
            """运行知识库维护任务的线程函数"""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(maintain_knowledge_database())
            except Exception as e:
                logger.error(f"知识库维护线程异常: {str(e)}")
            finally:
                loop.close()
                logger.info("知识库维护线程已结束")
        
        # 创建并启动维护线程
        self.maintenance_thread = threading.Thread(
            target=run_maintenance_thread, 
            daemon=True,
            name="KnowledgeMaintenanceThread"
        )
        self.maintenance_thread.start()
        
        logger.info("知识库维护任务已启动")
        return "知识库维护任务已成功启动，将定期执行优化、清理和合并操作"


# 注册工具
register_tool(KnowledgeManagerTool) 