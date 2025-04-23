import time
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from log import logger

class KnowledgeStore:
    def __init__(self, mongo_uri, database_name):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[database_name]
        self.knowledge_collection = self.db.knowledge

    async def get_embedding(self, query: str):
        # This method should be implemented to return the embedding for a given query
        # It should return a list of floats representing the embedding
        # For example, it could use a pre-trained model to generate the embedding
        pass

    async def search_knowledge(self, query: str, top_k: int = 3, min_similarity: float = 0.6, 
                       prioritize_recent: bool = False, ttl_check: bool = True) -> list:
        """
        从数据库中检索与查询最相关的知识记录
        :param query: 用户的查询
        :param top_k: 返回的最大结果数
        :param min_similarity: 最小相似度阈值
        :param prioritize_recent: 是否优先返回最近的内容，设为True时会加入时间权重
        :param ttl_check: 是否检查TTL，默认为True
        :return: 与查询最相关的知识记录列表
        """
        try:
            # 获取查询的嵌入向量
            query_embedding = await self.get_embedding(query)
            
            if not query_embedding:
                logger.error("无法获取查询的嵌入向量")
                return []
            
            # 设置基本的时间和TTL条件
            current_time = time.time()
            match_conditions = {}
            
            # 添加TTL检查
            if ttl_check:
                ttl_condition = {
                    "$or": [
                        {"ttl": {"$exists": False}},  # 没有设置TTL
                        {"ttl": None},  # TTL为空
                        {"$expr": {"$gt": [{"$add": ["$timestamp", "$ttl"]}, current_time]}}  # TTL未过期
                    ]
                }
                match_conditions.update(ttl_condition)
            
            # 构建聚合管道
            pipeline = [
                {"$match": match_conditions},
                {
                    "$addFields": {
                        "similarity": {
                            "$reduce": {
                                "input": {"$range": [0, {"$size": "$embedding"}]},
                                "initialValue": 0,
                                "in": {
                                    "$add": [
                                        "$$value",
                                        {"$multiply": [
                                            {"$arrayElemAt": ["$embedding", "$$this"]},
                                            {"$arrayElemAt": [query_embedding, "$$this"]}
                                        ]}
                                    ]
                                }
                            }
                        }
                    }
                },
                {"$match": {"similarity": {"$gte": min_similarity}}},
            ]
            
            # 添加时间权重计算
            if prioritize_recent:
                # 计算recency_score: 0到1之间的值，越新的内容得分越高
                # 使用对数衰减确保较旧但仍有价值的内容不会过度减分
                max_age_days = 30  # 设置最大考虑期限为30天
                pipeline.append({
                    "$addFields": {
                        "age_days": {"$divide": [{"$subtract": [current_time, "$timestamp"]}, 86400]},  # 计算天数
                        "recency_score": {
                            "$cond": {
                                "if": {"$gt": [{"$divide": [{"$subtract": [current_time, "$timestamp"]}, 86400]}, max_age_days]},
                                "then": 0.3,  # 超过30天的内容获得基础分0.3
                                "else": {
                                    "$subtract": [
                                        1, 
                                        {"$divide": [
                                            {"$ln": {"$add": [{"$divide": [{"$subtract": [current_time, "$timestamp"]}, 86400]}, 1]}},
                                            {"$ln": {"$add": [max_age_days, 1]}}
                                        ]}
                                    ]
                                }
                            }
                        }
                    }
                })
                
                # 计算组合分数：相似度 * 0.6 + 时效性 * 0.3 + 重要性 * 0.1
                pipeline.append({
                    "$addFields": {
                        "combined_score": {
                            "$add": [
                                {"$multiply": ["$similarity", 0.6]},
                                {"$multiply": ["$recency_score", 0.3]},
                                {"$multiply": [{"$ifNull": ["$importance", 0.5]}, 0.1]}
                            ]
                        }
                    }
                })
                
                # 按组合分数排序
                pipeline.append({"$sort": {"combined_score": -1}})
                
            else:
                # 传统排序：先按相似度，再按重要性
                pipeline.append({
                    "$sort": {
                        "similarity": -1,
                        "importance": -1
                    }
                })
            
            # 限制返回结果数量
            pipeline.append({"$limit": top_k})
            
            # 投影需要的字段
            pipeline.append({
                "$project": {
                    "_id": 1,
                    "content": 1, 
                    "query": 1,
                    "source": 1,
                    "timestamp": 1,
                    "tags": 1,
                    "importance": 1,
                    "similarity": 1,
                    "recency_score": {"$ifNull": ["$recency_score", 0]},
                    "combined_score": {"$ifNull": ["$combined_score", "$similarity"]},
                    "age_days": {"$ifNull": ["$age_days", {"$divide": [{"$subtract": [current_time, "$timestamp"]}, 86400]}]},
                    "verification": 1
                }
            })
            
            # 执行聚合查询
            result = []
            async for doc in self.knowledge_collection.aggregate(pipeline):
                # 转换ObjectId为字符串，以便于JSON序列化
                doc["_id"] = str(doc["_id"])
                result.append(doc)
            
            logger.info(f"检索到 {len(result)} 条知识记录")
            
            # 记录检索细节用于调试
            if prioritize_recent and result:
                for idx, item in enumerate(result):
                    logger.debug(f"结果 #{idx+1}: 相似度={item.get('similarity', 0):.4f}, "
                               f"时效分={item.get('recency_score', 0):.4f}, "
                               f"年龄={item.get('age_days', 0):.1f}天, "
                               f"组合分={item.get('combined_score', 0):.4f}")
            
            return result
            
        except Exception as e:
            logger.error(f"搜索知识失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return [] 