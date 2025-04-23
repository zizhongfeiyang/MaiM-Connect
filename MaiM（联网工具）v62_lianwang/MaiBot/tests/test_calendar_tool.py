import unittest
import asyncio
from datetime import datetime, timedelta
from src.do_tool.tool_can_use.calendar_tool import CalendarTool


class CalendarToolTest(unittest.TestCase):
    """日历工具测试类"""

    def setUp(self):
        """测试前设置"""
        self.calendar_tool = CalendarTool()
        # 清空事件列表
        self.calendar_tool.events = []

    async def test_add_event(self):
        """测试添加事件功能"""
        # 准备测试数据
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        
        function_args = {
            "action": "add",
            "title": "测试会议",
            "date": tomorrow,
            "time": "14:00",
            "duration": 60,
            "description": "这是一个测试会议"
        }
        
        # 执行工具方法
        result = await self.calendar_tool.execute(function_args)
        
        # 验证结果
        self.assertEqual(result["name"], "calendar")
        self.assertIn("已成功添加事件", result["content"])
        self.assertEqual(len(self.calendar_tool.events), 1)
        self.assertEqual(self.calendar_tool.events[0]["title"], "测试会议")

    async def test_check_events(self):
        """测试查询事件功能"""
        # 添加测试数据
        tomorrow = (datetime.now() + timedelta(days=1))
        tomorrow_str = tomorrow.strftime('%Y-%m-%d')
        
        # 添加一个事件
        self.calendar_tool.events.append({
            "id": "test_id_1",
            "title": "测试会议1",
            "datetime": tomorrow.replace(hour=14, minute=0),
            "duration": 60,
            "description": "这是测试会议1",
            "created_at": datetime.now()
        })
        
        # 添加第二个事件（两天后）
        day_after_tomorrow = (datetime.now() + timedelta(days=2))
        self.calendar_tool.events.append({
            "id": "test_id_2",
            "title": "测试会议2",
            "datetime": day_after_tomorrow.replace(hour=10, minute=30),
            "duration": 90,
            "description": "这是测试会议2",
            "created_at": datetime.now()
        })
        
        # 测试1: 查询特定日期
        function_args = {
            "action": "check",
            "date": tomorrow_str
        }
        
        result = await self.calendar_tool.execute(function_args)
        
        # 验证结果
        self.assertEqual(result["name"], "calendar")
        self.assertIn("找到1个事件", result["content"])
        self.assertIn("测试会议1", result["content"])
        self.assertNotIn("测试会议2", result["content"])
        
        # 测试2: 查询未来7天
        function_args = {
            "action": "check",
            "days": 7
        }
        
        result = await self.calendar_tool.execute(function_args)
        
        # 验证结果
        self.assertEqual(result["name"], "calendar")
        self.assertIn("找到2个事件", result["content"])
        self.assertIn("测试会议1", result["content"])
        self.assertIn("测试会议2", result["content"])

    async def test_remove_event(self):
        """测试删除事件功能"""
        # 添加测试数据
        tomorrow = (datetime.now() + timedelta(days=1))
        
        self.calendar_tool.events.append({
            "id": "test_id_to_remove",
            "title": "要删除的会议",
            "datetime": tomorrow.replace(hour=14, minute=0),
            "duration": 60,
            "description": "这是要删除的会议",
            "created_at": datetime.now()
        })
        
        # 执行删除
        function_args = {
            "action": "remove",
            "event_id": "test_id_to_remove"
        }
        
        result = await self.calendar_tool.execute(function_args)
        
        # 验证结果
        self.assertEqual(result["name"], "calendar")
        self.assertIn("已成功删除事件", result["content"])
        self.assertEqual(len(self.calendar_tool.events), 0)
        
        # 测试删除不存在的事件
        function_args = {
            "action": "remove",
            "event_id": "non_existent_id"
        }
        
        result = await self.calendar_tool.execute(function_args)
        
        # 验证结果
        self.assertEqual(result["name"], "calendar")
        self.assertIn("未找到ID", result["content"])


def run_async_test(test_func):
    """运行异步测试函数的帮助函数"""
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_func())


if __name__ == "__main__":
    """运行测试"""
    # 创建测试实例
    test = CalendarToolTest()
    
    # 设置
    test.setUp()
    
    # 运行测试
    print("测试添加事件...")
    run_async_test(test.test_add_event)
    
    print("\n测试查询事件...")
    test.setUp()  # 重置状态
    run_async_test(test.test_check_events)
    
    print("\n测试删除事件...")
    test.setUp()  # 重置状态
    run_async_test(test.test_remove_event)
    
    print("\n所有测试完成!") 