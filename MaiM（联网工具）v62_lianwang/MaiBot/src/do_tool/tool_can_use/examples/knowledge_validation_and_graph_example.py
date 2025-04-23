from src.do_tool.tool_use import ToolUser
import asyncio
from src.plugins.chat.chat_stream import ChatStream
import json
from datetime import datetime
from src.do_tool.tool_can_use.store_knowledge import StoreKnowledgeTool

async def knowledge_validation_and_graph_example():
    """
    知识验证和知识图谱功能示例

    该示例演示如何使用增强版知识存储工具的知识验证和知识图谱功能。
    """
    # 创建工具用户
    tool_user = ToolUser()
    
    # 模拟聊天流程
    chat_stream = ChatStream(stream_id="example_stream")
    
    # 创建知识存储工具实例
    knowledge_tool = StoreKnowledgeTool()
    
    # 示例1: 验证准确的知识内容
    print("\n=== 示例1: 知识验证（准确内容） ===")
    message_txt = "请记录这个事实: 人工智能研究始于20世纪50年代，图灵测试由艾伦·图灵于1950年提出。"
    
    # 通过工具用户调用
    result = await tool_user.use_tool(message_txt=message_txt, sender_name="用户", chat_stream=chat_stream)
    
    if result["used_tools"]:
        print("工具调用成功！")
        print(json.dumps(result["structured_info"], indent=2, ensure_ascii=False))
    else:
        print("工具调用失败或未使用工具")
    
    # 示例2: 验证包含错误信息的内容
    print("\n=== 示例2: 知识验证（错误内容） ===")
    function_args = {
        "query": "错误知识测试",
        "content": "地球是平的，这是一个被广泛接受的科学事实。",
        "source": "test",
        "verify_facts": True
    }
    
    result = await knowledge_tool.execute(function_args)
    print("直接工具调用结果:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 示例3: 使用实体抽取和关系识别功能
    print("\n=== 示例3: 实体和关系抽取 ===")
    function_args = {
        "query": "技术实体关系测试",
        "content": "深度学习是人工智能的一个子领域。谷歌公司位于美国，它广泛使用深度学习技术。李飞飞是斯坦福大学的教授，她是计算机视觉领域的专家。",
        "source": "test_input",
        "extract_entities": True
    }
    
    result = await knowledge_tool.execute(function_args)
    print("实体和关系抽取结果:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 获取存储的知识ID
    knowledge_id = result.get("knowledge_id")
    
    if knowledge_id:
        # 示例4: 存储关联知识，形成知识图谱
        print("\n=== 示例4: 创建知识图谱关联 ===")
        function_args = {
            "query": "图谱关联测试",
            "content": "卷积神经网络(CNN)是深度学习的重要组成部分，它特别适合于图像识别任务。谷歌的TensorFlow是一个流行的深度学习框架。",
            "source": "test_input",
            "related_to": knowledge_id,
            "tags": ["深度学习", "神经网络"],
            "extract_entities": True
        }
        
        result = await knowledge_tool.execute(function_args)
        print("关联知识存储结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # 示例5: 搜索知识图谱
        print("\n=== 示例5: 搜索知识图谱 ===")
        entity = "深度学习"
        graph_results = await knowledge_tool.search_knowledge_graph(entity)
        
        print(f"关于'{entity}'的知识图谱关系:")
        print(json.dumps(graph_results, indent=2, ensure_ascii=False))
    else:
        print("未获取到知识ID，跳过知识图谱示例")


if __name__ == "__main__":
    """运行示例"""
    asyncio.run(knowledge_validation_and_graph_example()) 