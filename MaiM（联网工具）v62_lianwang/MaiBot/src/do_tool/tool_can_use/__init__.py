from src.do_tool.tool_can_use.base_tool import (
    BaseTool,
    register_tool,
    discover_tools,
    get_all_tool_definitions,
    get_tool_instance,
    TOOL_REGISTRY,
)

# 导入新工具
from src.do_tool.tool_can_use.search_engine_tool import SearchEngineTool

__all__ = [
    "BaseTool",
    "register_tool",
    "discover_tools",
    "get_all_tool_definitions",
    "get_tool_instance",
    "TOOL_REGISTRY",
    "SearchEngineTool",  # 添加到导出列表
]

# 显式注册新工具
register_tool(SearchEngineTool)

# 自动发现并注册工具
discover_tools()
