from src.do_tool.tool_use import ToolUser
import asyncio
from src.plugins.chat.chat_stream import ChatStream
import json
from datetime import datetime

async def store_knowledge_example():
    """
    知识存储工具使用示例

    该示例演示如何使用优化后的知识存储工具来存储和管理知识。
    """
    # 创建工具用户
    tool_user = ToolUser()
    
    # 模拟聊天流程
    chat_stream = ChatStream(stream_id="example_stream")
    
    # 示例1: 存储基本知识
    print("\n=== 示例1: 存储基本知识 ===")
    message_txt = "帮我记住一个重要知识: 人工智能是计算机科学的一个分支，致力于创建能够模拟人类智能的系统。"
    result = await tool_user.use_tool(message_txt=message_txt, sender_name="用户", chat_stream=chat_stream)
    
    if result["used_tools"]:
        print("工具调用成功！")
        print(json.dumps(result["structured_info"], indent=2, ensure_ascii=False))
    else:
        print("工具调用失败或未使用工具")
    
    # 示例2: 使用标签和重要度存储知识
    print("\n=== 示例2: 使用标签和重要度存储知识 ===")
    message_txt = "请将这条信息作为重要知识储存并标记为AI技术: 深度学习是机器学习的一个子集，使用多层神经网络进行数据处理和模式识别。"
    result = await tool_user.use_tool(message_txt=message_txt, sender_name="用户", chat_stream=chat_stream)
    
    if result["used_tools"]:
        print("工具调用成功！")
        print(json.dumps(result["structured_info"], indent=2, ensure_ascii=False))
    else:
        print("工具调用失败或未使用工具")
    
    # 示例3: 尝试存储相似内容
    print("\n=== 示例3: 尝试存储相似内容 ===")
    message_txt = "请记住: 深度学习是AI的一种技术，使用神经网络进行数据处理。"
    result = await tool_user.use_tool(message_txt=message_txt, sender_name="用户", chat_stream=chat_stream)
    
    if result["used_tools"]:
        print("工具调用成功！")
        print(json.dumps(result["structured_info"], indent=2, ensure_ascii=False))
    else:
        print("工具调用失败或未使用工具")
    
    # 示例4: 使用override_similar参数覆盖相似内容
    print("\n=== 示例4: 覆盖相似内容 ===")
    message_txt = "请更新之前关于深度学习的知识: 深度学习是使用人工神经网络的机器学习方法，它模仿人脑结构和功能，可以从大量数据中学习复杂模式。"
    result = await tool_user.use_tool(message_txt=message_txt, sender_name="用户", chat_stream=chat_stream)
    
    if result["used_tools"]:
        print("工具调用成功！")
        print(json.dumps(result["structured_info"], indent=2, ensure_ascii=False))
    else:
        print("工具调用失败或未使用工具")
    
    # 示例5: 使用关联知识存储
    print("\n=== 示例5: 关联知识存储 ===")
    # 假设我们已经从示例2中获取了一个知识ID
    knowledge_id = result["structured_info"].get("knowledge_id", "")
    message_txt = f"请记住并关联到之前的深度学习知识: 卷积神经网络(CNN)是深度学习中常用的一种网络结构，特别适合于图像识别和处理任务。"
    
    if knowledge_id:
        # 手动构建工具调用，以便直接测试工具功能
        from src.do_tool.tool_can_use.store_knowledge import StoreKnowledgeTool
        
        tool = StoreKnowledgeTool()
        function_args = {
            "query": "卷积神经网络知识",
            "content": "卷积神经网络(CNN)是深度学习中常用的一种网络结构，特别适合于图像识别和处理任务。",
            "source": "user_input",
            "tags": ["AI技术", "神经网络", "CNN"],
            "importance": 4,
            "related_to": knowledge_id
        }
        
        result = await tool.execute(function_args)
        print("直接工具调用结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("未获取到前一个知识的ID，跳过关联知识存储示例")


if __name__ == "__main__":
    """运行示例"""
    asyncio.run(store_knowledge_example()) 