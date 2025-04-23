from src.do_tool.tool_use import ToolUser
import asyncio
from src.plugins.chat.chat_stream import ChatStream
import json

async def calendar_tool_example():
    """
    日历工具使用示例

    该示例演示如何使用日历工具来添加、查询和删除日历事件。
    """
    # 创建工具用户
    tool_user = ToolUser()
    
    # 模拟聊天流程
    chat_stream = ChatStream(stream_id="example_stream")
    
    # 示例1: 添加事件
    print("\n=== 示例1: 添加日历事件 ===")
    message_txt = "帮我记录一下明天下午2点要和张经理开会，大约需要1小时"
    result = await tool_user.use_tool(message_txt=message_txt, sender_name="用户", chat_stream=chat_stream)
    
    if result["used_tools"]:
        print("工具调用成功！")
        print(json.dumps(result["structured_info"], indent=2, ensure_ascii=False))
    else:
        print("工具调用失败或未使用工具")
    
    # 示例2: 查询事件
    print("\n=== 示例2: 查询日历事件 ===")
    message_txt = "帮我看看我这周有哪些安排"
    result = await tool_user.use_tool(message_txt=message_txt, sender_name="用户", chat_stream=chat_stream)
    
    if result["used_tools"]:
        print("工具调用成功！")
        print(json.dumps(result["structured_info"], indent=2, ensure_ascii=False))
    else:
        print("工具调用失败或未使用工具")
    
    # 示例3: 删除事件
    print("\n=== 示例3: 删除日历事件 ===")
    # 假设我们已经从示例1中获取了一个事件ID
    message_txt = "帮我取消明天和张经理的会议"
    result = await tool_user.use_tool(message_txt=message_txt, sender_name="用户", chat_stream=chat_stream)
    
    if result["used_tools"]:
        print("工具调用成功！")
        print(json.dumps(result["structured_info"], indent=2, ensure_ascii=False))
    else:
        print("工具调用失败或未使用工具")


if __name__ == "__main__":
    """运行示例"""
    asyncio.run(calendar_tool_example()) 