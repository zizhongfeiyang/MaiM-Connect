import unittest
import asyncio
from datetime import datetime
from src.do_tool.tool_can_use.store_knowledge import StoreKnowledgeTool
from unittest.mock import patch, MagicMock

class StoreKnowledgeToolTest(unittest.TestCase):
    """知识存储工具测试类"""

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
        except Exception as e:
            print(f"清理测试数据失败: {str(e)}")

    @patch('src.plugins.chat.utils.get_embedding')
    @patch('src.do_tool.tool_can_use.store_knowledge.db')
    async def test_store_basic_knowledge(self, mock_db, mock_get_embedding):
        """测试基本知识存储功能"""
        # 设置模拟
        mock_get_embedding.return_value = [0.1, 0.2, 0.3]
        mock_db.knowledges.insert_one.return_value = MagicMock(inserted_id="test_id_1")
        mock_db.knowledges.index_information.return_value = {}
        
        # 准备测试数据
        function_args = {
            "query": "test_basic_knowledge",
            "content": "这是一条测试知识",
            "source": "test"
        }
        
        # 执行工具方法
        result = await self.store_knowledge_tool.execute(function_args)
        
        # 验证结果
        self.assertEqual(result["name"], "store_knowledge")
        self.assertIn("成功存储", result["content"])
        self.assertEqual(result["knowledge_id"], "test_id_1")
        
        # 验证方法调用
        mock_get_embedding.assert_called_once()
        mock_db.knowledges.insert_one.assert_called_once()

    @patch('src.plugins.chat.utils.get_embedding')
    @patch('src.do_tool.tool_can_use.store_knowledge.db')
    async def test_store_knowledge_with_tags_and_importance(self, mock_db, mock_get_embedding):
        """测试带标签和重要度的知识存储功能"""
        # 设置模拟
        mock_get_embedding.return_value = [0.1, 0.2, 0.3]
        mock_db.knowledges.insert_one.return_value = MagicMock(inserted_id="test_id_2")
        mock_db.knowledges.index_information.return_value = {}
        
        # 准备测试数据
        function_args = {
            "query": "test_tags_importance",
            "content": "这是一条带标签和重要度的测试知识",
            "tags": ["测试", "标签"],
            "importance": 5
        }
        
        # 执行工具方法
        result = await self.store_knowledge_tool.execute(function_args)
        
        # 验证结果
        self.assertEqual(result["name"], "store_knowledge")
        self.assertIn("成功存储", result["content"])
        self.assertEqual(result["importance"], 5)
        self.assertEqual(result["tags"], ["测试", "标签"])
        
        # 验证方法调用
        mock_get_embedding.assert_called_once()
        # 验证插入的知识包含标签和重要度
        args, _ = mock_db.knowledges.insert_one.call_args
        self.assertEqual(args[0]["tags"], ["测试", "标签"])
        self.assertEqual(args[0]["importance"], 5)

    @patch('src.plugins.chat.utils.get_embedding')
    @patch('src.do_tool.tool_can_use.store_knowledge.db')
    async def test_similar_content_detection(self, mock_db, mock_get_embedding):
        """测试相似内容检测功能"""
        # 设置模拟
        mock_get_embedding.return_value = [0.1, 0.2, 0.3]
        # 模拟找到相似内容
        mock_db.knowledges.aggregate.return_value = [{
            "_id": "similar_id",
            "content": "这是一条相似内容",
            "similarity": 0.95
        }]
        
        # 准备测试数据
        function_args = {
            "query": "test_similar_content",
            "content": "这是一条测试相似内容",
            "override_similar": False
        }
        
        # 执行工具方法
        result = await self.store_knowledge_tool.execute(function_args)
        
        # 验证结果
        self.assertEqual(result["name"], "store_knowledge")
        self.assertIn("已存在相似内容", result["content"])
        self.assertIn("0.95", result["content"])  # 检查相似度是否包含在结果中
        
        # 验证没有插入新内容
        mock_db.knowledges.insert_one.assert_not_called()

    @patch('src.plugins.chat.utils.get_embedding')
    @patch('src.do_tool.tool_can_use.store_knowledge.db')
    async def test_override_similar_content(self, mock_db, mock_get_embedding):
        """测试覆盖相似内容功能"""
        # 设置模拟
        mock_get_embedding.return_value = [0.1, 0.2, 0.3]
        # 模拟找到相似内容
        mock_db.knowledges.aggregate.return_value = [{
            "_id": "similar_id",
            "content": "这是一条相似内容",
            "similarity": 0.95,
            "tags": ["旧标签"]
        }]
        
        # 准备测试数据
        function_args = {
            "query": "test_override_similar",
            "content": "这是一条更新的内容",
            "tags": ["新标签"],
            "importance": 4,
            "override_similar": True
        }
        
        # 执行工具方法
        result = await self.store_knowledge_tool.execute(function_args)
        
        # 验证结果
        self.assertEqual(result["name"], "store_knowledge")
        self.assertIn("已更新现有知识", result["content"])
        
        # 验证更新操作
        mock_db.knowledges.update_one.assert_called_once()
        args, _ = mock_db.knowledges.update_one.call_args
        self.assertEqual(args[0], {"_id": "similar_id"})
        # 验证更新内容
        update_data = args[1]
        self.assertEqual(update_data["$set"]["content"], "这是一条更新的内容")
        self.assertEqual(update_data["$set"]["importance"], 4)

    @patch('src.plugins.chat.utils.get_embedding')
    async def test_search_knowledge(self, mock_get_embedding):
        """测试知识搜索辅助方法"""
        # 设置模拟
        mock_get_embedding.return_value = [0.1, 0.2, 0.3]
        
        # 模拟数据库返回
        with patch('src.do_tool.tool_can_use.store_knowledge.db') as mock_db:
            mock_db.knowledges.aggregate.return_value = [
                {
                    "_id": "result_id_1",
                    "content": "搜索结果1",
                    "tags": ["测试", "搜索"],
                    "importance": 5,
                    "created_at": datetime.now(),
                    "source": "test",
                    "similarity": 0.9
                },
                {
                    "_id": "result_id_2",
                    "content": "搜索结果2",
                    "tags": ["测试"],
                    "importance": 3,
                    "created_at": datetime.now(),
                    "source": "test",
                    "similarity": 0.8
                }
            ]
            
            # 执行搜索
            results = await self.store_knowledge_tool.search_knowledge(
                query="测试搜索",
                tags=["测试"],
                limit=5
            )
            
            # 验证结果
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0]["_id"], "result_id_1")
            self.assertEqual(results[0]["similarity"], 0.9)
            
            # 验证更新访问计数
            self.assertEqual(mock_db.knowledges.update_one.call_count, 2)

    def test_ensure_indexes(self):
        """测试索引确保功能"""
        with patch('src.do_tool.tool_can_use.store_knowledge.db') as mock_db:
            # 模拟没有索引
            mock_db.knowledges.index_information.return_value = {}
            
            # 执行方法
            self.store_knowledge_tool._ensure_indexes()
            
            # 验证创建索引的调用
            self.assertEqual(mock_db.knowledges.create_index.call_count, 4)
            
            # 测试已有部分索引的情况
            mock_db.knowledges.create_index.reset_mock()
            mock_db.knowledges.index_information.return_value = {
                "importance_1": {},
                "tags_1": {}
            }
            
            # 执行方法
            self.store_knowledge_tool._ensure_indexes()
            
            # 验证只创建缺失的索引
            self.assertEqual(mock_db.knowledges.create_index.call_count, 2)


def run_async_test(test_func):
    """运行异步测试函数的帮助函数"""
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_func())


if __name__ == "__main__":
    """运行测试"""
    # 创建测试实例
    test = StoreKnowledgeToolTest()
    
    # 设置
    test.setUp()
    
    # 运行测试
    print("测试基本知识存储...")
    run_async_test(test.test_store_basic_knowledge)
    
    print("\n测试标签和重要度...")
    test.setUp()  # 重置状态
    run_async_test(test.test_store_knowledge_with_tags_and_importance)
    
    print("\n测试相似内容检测...")
    test.setUp()  # 重置状态
    run_async_test(test.test_similar_content_detection)
    
    print("\n测试覆盖相似内容...")
    test.setUp()  # 重置状态
    run_async_test(test.test_override_similar_content)
    
    print("\n测试知识搜索...")
    test.setUp()  # 重置状态
    run_async_test(test.test_search_knowledge)
    
    print("\n测试索引确保...")
    test.setUp()  # 重置状态
    test.test_ensure_indexes()
    
    print("\n所有测试完成!")
    
    # 清理
    test.clean_test_data() 