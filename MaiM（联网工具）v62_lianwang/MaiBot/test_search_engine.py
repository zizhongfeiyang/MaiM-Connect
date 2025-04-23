import asyncio
from src.do_tool.tool_can_use.search_engine_tool import SearchEngineTool

async def test_search_engine():
    """测试智能搜索引擎工具"""
    try:
        print("开始测试智能搜索引擎工具...")
        search_engine = SearchEngineTool()
        
        # 测试查询
        test_query = "人工智能最新发展"
        print(f"测试查询: {test_query}")
        
        # 执行搜索
        result = await search_engine.execute({
            "query": test_query,
            "chat_id": "test_chat",
            "force_web_search": True
        })
        
        # 打印结果
        print("\n搜索结果:")
        if result and "content" in result:
            print(result["content"])
        else:
            print("搜索失败或无结果")
            print(result)
        
        print("\n测试完成")
        
    except Exception as e:
        print(f"测试过程中出错: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_search_engine()) 