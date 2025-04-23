import unittest
import asyncio
from datetime import datetime
from src.do_tool.tool_can_use.store_knowledge import StoreKnowledgeTool
from unittest.mock import patch, MagicMock, call

class KnowledgeValidationAndGraphTest(unittest.TestCase):
    """知识验证和知识图谱功能测试类"""

    def setUp(self):
        """测试前设置"""
        self.store_knowledge_tool = StoreKnowledgeTool()
        # 清理测试数据
        self.clean_test_data()
    
    def clean_test_data(self):
        """清理测试数据"""
        try:
            from src.common.database import db
            # 删除测试过程中创建的所有测试数据
            db.knowledges.delete_many({"query": {"$regex": "^test_"}})
            db.knowledge_graph.delete_many({"subject": {"$regex": "^test_"}})
        except Exception as e:
            print(f"清理测试数据失败: {str(e)}")

    @patch('src.do_tool.tool_can_use.store_knowledge.StoreKnowledgeTool._verify_facts')
    @patch('src.plugins.chat.utils.get_embedding')
    @patch('src.do_tool.tool_can_use.store_knowledge.db')
    async def test_fact_verification_pass(self, mock_db, mock_get_embedding, mock_verify_facts):
        """测试事实验证通过的情况"""
        # 设置模拟
        mock_get_embedding.return_value = [0.1, 0.2, 0.3]
        mock_db.knowledges.insert_one.return_value = MagicMock(inserted_id="test_id_1")
        mock_db.knowledges.index_information.return_value = {}
        
        # 模拟验证结果 - 通过
        verification_result = {
            "is_factual": True,
            "confidence": 0.9,
            "reason": "验证通过",
            "verified_at": datetime.now()
        }
        mock_verify_facts.return_value = verification_result
        
        # 准备测试数据
        function_args = {
            "query": "test_verification_pass",
            "content": "这是一条正确的知识",
            "verify_facts": True
        }
        
        # 执行工具方法
        result = await self.store_knowledge_tool.execute(function_args)
        
        # 验证结果
        self.assertEqual(result["name"], "store_knowledge")
        self.assertIn("成功存储", result["content"])
        self.assertEqual(result["verification"], verification_result)
        
        # 验证方法调用
        mock_verify_facts.assert_called_once_with("这是一条正确的知识")
        # 验证插入的知识包含验证结果
        args, _ = mock_db.knowledges.insert_one.call_args
        self.assertEqual(args[0]["verification"], verification_result)

    @patch('src.do_tool.tool_can_use.store_knowledge.StoreKnowledgeTool._verify_facts')
    @patch('src.plugins.chat.utils.get_embedding')
    @patch('src.do_tool.tool_can_use.store_knowledge.db')
    async def test_fact_verification_fail(self, mock_db, mock_get_embedding, mock_verify_facts):
        """测试事实验证失败的情况"""
        # 设置模拟
        mock_get_embedding.return_value = [0.1, 0.2, 0.3]
        
        # 模拟验证结果 - 失败
        verification_result = {
            "is_factual": False,
            "confidence": 0.95,
            "reason": "内容包含错误信息",
            "verified_at": datetime.now()
        }
        mock_verify_facts.return_value = verification_result
        
        # 准备测试数据
        function_args = {
            "query": "test_verification_fail",
            "content": "地球是平的",
            "verify_facts": True
        }
        
        # 执行工具方法
        result = await self.store_knowledge_tool.execute(function_args)
        
        # 验证结果
        self.assertEqual(result["name"], "store_knowledge")
        self.assertIn("知识验证失败", result["content"])
        self.assertEqual(result["verification"], verification_result)
        
        # 验证没有插入知识
        mock_db.knowledges.insert_one.assert_not_called()

    @patch('src.do_tool.tool_can_use.store_knowledge.StoreKnowledgeTool._extract_entities_and_relations')
    @patch('src.plugins.chat.utils.get_embedding')
    @patch('src.do_tool.tool_can_use.store_knowledge.db')
    async def test_entity_extraction(self, mock_db, mock_get_embedding, mock_extract_entities):
        """测试实体抽取功能"""
        # 设置模拟
        mock_get_embedding.return_value = [0.1, 0.2, 0.3]
        mock_db.knowledges.insert_one.return_value = MagicMock(inserted_id="test_id_2")
        mock_db.knowledges.index_information.return_value = {}
        
        # 模拟实体抽取结果
        entities_and_relations = {
            "entities": ["深度学习", "计算机视觉", "谷歌"],
            "relations": [
                {"subject": "深度学习", "predicate": "属于", "object": "人工智能"},
                {"subject": "谷歌", "predicate": "使用", "object": "深度学习"}
            ]
        }
        mock_extract_entities.return_value = entities_and_relations
        
        # 准备测试数据
        function_args = {
            "query": "test_entity_extraction",
            "content": "深度学习是人工智能的一个分支，谷歌使用深度学习技术进行计算机视觉研究。",
            "extract_entities": True
        }
        
        # 执行工具方法
        result = await self.store_knowledge_tool.execute(function_args)
        
        # 验证结果
        self.assertEqual(result["name"], "store_knowledge")
        self.assertIn("成功存储", result["content"])
        self.assertEqual(result["entities"], entities_and_relations["entities"])
        
        # 验证方法调用
        mock_extract_entities.assert_called_once()
        # 验证插入的知识包含实体和关系
        args, _ = mock_db.knowledges.insert_one.call_args
        self.assertEqual(args[0]["entities"], entities_and_relations["entities"])
        self.assertEqual(args[0]["relations"], entities_and_relations["relations"])
        
        # 验证标签是否包含提取的实体
        for entity in entities_and_relations["entities"]:
            self.assertIn(entity.lower(), args[0]["tags"])

    @patch('src.do_tool.tool_can_use.store_knowledge.StoreKnowledgeTool._update_knowledge_graph')
    @patch('src.do_tool.tool_can_use.store_knowledge.StoreKnowledgeTool._extract_entities_and_relations')
    @patch('src.plugins.chat.utils.get_embedding')
    @patch('src.do_tool.tool_can_use.store_knowledge.db')
    async def test_knowledge_graph_update(self, mock_db, mock_get_embedding, 
                                          mock_extract_entities, mock_update_graph):
        """测试知识图谱更新功能"""
        # 设置模拟
        mock_get_embedding.return_value = [0.1, 0.2, 0.3]
        mock_db.knowledges.insert_one.return_value = MagicMock(inserted_id="test_id_3")
        mock_db.knowledges.index_information.return_value = {}
        
        # 模拟实体抽取结果
        relations = [
            {"subject": "test_subject", "predicate": "test_predicate", "object": "test_object"}
        ]
        mock_extract_entities.return_value = {
            "entities": ["test_subject", "test_object"],
            "relations": relations
        }
        
        # 准备测试数据
        function_args = {
            "query": "test_knowledge_graph",
            "content": "测试知识图谱更新功能",
            "extract_entities": True
        }
        
        # 执行工具方法
        result = await self.store_knowledge_tool.execute(function_args)
        
        # 验证结果
        self.assertEqual(result["name"], "store_knowledge")
        self.assertIn("成功存储", result["content"])
        
        # 验证知识图谱更新调用
        mock_update_graph.assert_called_once_with("test_id_3", relations)

    @patch('src.do_tool.tool_can_use.store_knowledge.db')
    async def test_search_knowledge_graph(self, mock_db):
        """测试知识图谱搜索功能"""
        # 模拟数据库返回
        mock_db.knowledge_graph.find.return_value = [
            {
                "_id": "graph_id_1",
                "subject": "test_entity",
                "predicate": "test_relation",
                "object": "test_related_entity",
                "source_knowledge_id": "test_id"
            },
            {
                "_id": "graph_id_2",
                "subject": "test_another_entity",
                "predicate": "test_another_relation",
                "object": "test_entity",
                "source_knowledge_id": "test_id"
            }
        ]
        
        # 执行搜索
        results = await self.store_knowledge_tool.search_knowledge_graph(
            entity="test_entity",
            relation_type=None,
            limit=10
        )
        
        # 验证结果
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["description"], "test_entity test_relation test_related_entity")
        self.assertEqual(results[1]["description"], "test_another_entity test_another_relation test_entity")
        
        # 验证查询条件
        mock_db.knowledge_graph.find.assert_called_once()
        args, _ = mock_db.knowledge_graph.find.call_args
        query = args[0]
        self.assertIn("$or", query)
        self.assertEqual(len(query["$or"]), 2)
        self.assertEqual(query["$or"][0]["subject"], "test_entity")
        self.assertEqual(query["$or"][1]["object"], "test_entity")
    
    @patch('src.do_tool.tool_can_use.store_knowledge.db')
    def test_update_reverse_relation(self, mock_db):
        """测试反向关联更新功能"""
        # 执行方法
        self.store_knowledge_tool._update_reverse_relation(
            knowledge_id="test_id_1",
            related_id="test_id_2"
        )
        
        # 验证更新操作
        mock_db.knowledges.update_one.assert_called_once()
        args, _ = mock_db.knowledges.update_one.call_args
        self.assertEqual(args[0], {"_id": "test_id_1"})
        self.assertEqual(args[1], {"$addToSet": {"related_to": "test_id_2"}})
    
    async def test_verify_facts_implementation(self):
        """测试事实验证具体实现"""
        # 测试错误内容
        result = await self.store_knowledge_tool._verify_facts("地球是平的，这是科学事实")
        self.assertFalse(result["is_factual"])
        self.assertGreater(result["confidence"], 0.8)
        
        # 测试正确内容
        result = await self.store_knowledge_tool._verify_facts("人工智能是计算机科学的一个分支")
        self.assertTrue(result["is_factual"])
    
    async def test_extract_entities_implementation(self):
        """测试实体抽取具体实现"""
        content = "谷歌公司位于美国，它使用深度学习技术。李飞飞是斯坦福大学的教授。"
        result = await self.store_knowledge_tool._extract_entities_and_relations(content)
        
        # 验证提取的实体
        entities = result["entities"]
        self.assertIn("谷歌公司", entities)
        self.assertIn("美国", entities)
        self.assertIn("深度学习", entities)
        
        # 验证提取的关系
        relations = result["relations"]
        has_location_relation = False
        has_use_relation = False
        
        for relation in relations:
            if relation["subject"] == "谷歌公司" and relation["predicate"] == "位于" and relation["object"] == "美国":
                has_location_relation = True
            if relation["subject"] == "谷歌公司" and relation["predicate"] == "使用" and relation["object"] == "深度学习":
                has_use_relation = True
        
        self.assertTrue(has_location_relation or has_use_relation)


def run_async_test(test_func):
    """运行异步测试函数的帮助函数"""
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_func())


if __name__ == "__main__":
    """运行测试"""
    # 创建测试实例
    test = KnowledgeValidationAndGraphTest()
    
    # 设置
    test.setUp()
    
    # 运行测试
    print("测试事实验证通过...")
    run_async_test(test.test_fact_verification_pass)
    
    print("\n测试事实验证失败...")
    test.setUp()  # 重置状态
    run_async_test(test.test_fact_verification_fail)
    
    print("\n测试实体抽取...")
    test.setUp()  # 重置状态
    run_async_test(test.test_entity_extraction)
    
    print("\n测试知识图谱更新...")
    test.setUp()  # 重置状态
    run_async_test(test.test_knowledge_graph_update)
    
    print("\n测试知识图谱搜索...")
    test.setUp()  # 重置状态
    run_async_test(test.test_search_knowledge_graph)
    
    print("\n测试反向关联更新...")
    test.setUp()  # 重置状态
    test.test_update_reverse_relation()
    
    print("\n测试事实验证具体实现...")
    test.setUp()  # 重置状态
    run_async_test(test.test_verify_facts_implementation)
    
    print("\n测试实体抽取具体实现...")
    test.setUp()  # 重置状态
    run_async_test(test.test_extract_entities_implementation)
    
    print("\n所有测试完成!")
    
    # 清理
    test.clean_test_data() 