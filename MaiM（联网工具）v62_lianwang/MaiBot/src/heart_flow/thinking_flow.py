# 在思考流程中查找工具调用部分的相关代码片段，并添加搜索去重逻辑

# 查找在同一思考流程中可能重复执行搜索的地方
# 添加一个变量来跟踪已经执行过的搜索查询

# 搜索工具调用记录器函数
async def record_tool_call(
    thinking_flow_id: str,
    tool_name: str,
    tool_args: dict,
    tool_result: dict,
):
    """记录工具调用，添加查询跟踪以防止重复搜索"""
    try:
        # 获取当前思考流程
        thinking_flow = await get_thinking_flow(thinking_flow_id)
        if not thinking_flow:
            logger.error(f"无法找到思考流程: {thinking_flow_id}")
            return
        
        # 记录工具调用
        tool_call = {
            "tool_name": tool_name,
            "args": tool_args,
            "result": tool_result,
            "timestamp": datetime.now().timestamp()
        }
        
        # 将工具调用添加到思考流程中
        if "tool_calls" not in thinking_flow:
            thinking_flow["tool_calls"] = []
        
        # 检查是否是web_search工具且已经在本次思考流程中执行过相同的查询
        if tool_name == "web_search" and "query" in tool_args:
            query = tool_args["query"]
            # 检查是否已经执行过相同的查询
            for existing_call in thinking_flow.get("tool_calls", []):
                if (existing_call.get("tool_name") == "web_search" and 
                    existing_call.get("args", {}).get("query") == query):
                    # 这个查询已经执行过，记录日志并返回
                    logger.info(f"在思考流程中跳过重复的搜索查询: {query}")
                    return
        
        # 如果是新的查询或非搜索工具，则添加到记录
        thinking_flow["tool_calls"].append(tool_call)
        
        # 更新思考流程
        await update_thinking_flow(thinking_flow_id, thinking_flow)
        
    except Exception as e:
        logger.error(f"记录工具调用时出错: {str(e)}") 