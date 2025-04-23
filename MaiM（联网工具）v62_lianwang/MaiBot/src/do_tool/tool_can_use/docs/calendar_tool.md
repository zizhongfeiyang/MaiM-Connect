# 日历工具 (Calendar Tool) 文档

## 功能概述

日历工具是一个用于管理用户日历事件的工具，它允许用户通过自然语言指令来添加、查询和删除日历事件。该工具继承自 `BaseTool` 基类，遵循 MaiBot 的工具系统架构。

## 主要功能

日历工具提供以下核心功能：

1. **添加事件** - 允许用户创建新的日历事件，包括标题、日期、时间、持续时间和描述等信息
2. **查询事件** - 允许用户查询特定日期或未来一段时间内的所有事件
3. **删除事件** - 允许用户删除指定的事件

## 参数说明

日历工具接受以下参数：

| 参数名 | 类型 | 描述 | 是否必需 |
|-------|------|------|---------|
| action | string | 要执行的操作：添加(add)、查询(check)或删除(remove)事件 | 是 |
| title | string | 事件标题 | 添加操作时必需 |
| date | string | 事件日期，格式为YYYY-MM-DD | 添加操作时必需 |
| time | string | 事件时间，格式为HH:MM，24小时制 | 否 |
| duration | integer | 事件持续时间（分钟） | 否，默认为60分钟 |
| description | string | 事件描述 | 否 |
| event_id | string | 事件ID，用于删除操作 | 删除操作时必需 |
| days | integer | 查询未来几天的事件，默认为7天 | 否 |

## 使用示例

### 1. 添加事件

```python
# 添加一个明天下午2点的会议
function_args = {
    "action": "add",
    "title": "与张经理会议",
    "date": "2023-10-15",  # 请使用实际的日期
    "time": "14:00",
    "duration": 60,
    "description": "讨论项目进度"
}

result = await calendar_tool.execute(function_args)
```

### 2. 查询事件

```python
# 查询特定日期的事件
function_args = {
    "action": "check",
    "date": "2023-10-15"  # 请使用实际的日期
}

result = await calendar_tool.execute(function_args)

# 查询未来7天的事件
function_args = {
    "action": "check",
    "days": 7
}

result = await calendar_tool.execute(function_args)
```

### 3. 删除事件

```python
# 删除特定事件
function_args = {
    "action": "remove",
    "event_id": "evt_1234567890"  # 使用实际的事件ID
}

result = await calendar_tool.execute(function_args)
```

## 自然语言使用

日历工具设计为可以通过自然语言指令使用。以下是一些示例：

- "帮我记录一下明天下午2点要和张经理开会，大约需要1小时"
- "查看我这周有哪些安排"
- "取消明天和张经理的会议"

LLM会解析这些自然语言指令并转换为适当的工具调用。

## 实现详情

### 核心方法

工具实现了以下核心方法：

- `_add_event()` - 处理添加事件的逻辑
- `_check_events()` - 处理查询事件的逻辑
- `_remove_event()` - 处理删除事件的逻辑
- `execute()` - 主入口方法，根据action参数调用对应的处理方法

### 存储机制

当前版本使用内存存储事件数据，在生产环境中，应该将事件存储在数据库中：

- `_load_events()` - 从存储加载事件
- `_save_events()` - 保存事件到存储

### 错误处理

工具实现了全面的错误处理机制：

- 参数验证 - 检查必需参数是否存在
- 日期时间解析错误处理
- 事件查找错误处理

所有操作都包含在try-except块中，确保任何错误都能被适当地捕获和处理。

## 扩展建议

以下是一些可能的扩展方向：

1. **持久化存储** - 将事件存储在MongoDB或其他数据库中，而不是内存中
2. **重复事件** - 添加对重复事件的支持（如每周一次、每月一次等）
3. **提醒功能** - 添加事件提醒功能
4. **共享日历** - 支持在多个用户之间共享日历事件
5. **导入/导出** - 支持导入和导出标准日历格式（如iCalendar）

## 测试

可以使用 `tests/test_calendar_tool.py` 来测试日历工具的功能。测试覆盖了添加、查询和删除事件的主要功能。 