from src.do_tool.tool_can_use.base_tool import BaseTool, register_tool
from src.common.logger import get_module_logger
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json

logger = get_module_logger("calendar_tool")


class CalendarTool(BaseTool):
    """日历事件管理工具"""

    name = "calendar"
    description = "管理用户的日历事件，可以添加、查询和删除事件"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "check", "remove"],
                "description": "要执行的操作：添加(add)、查询(check)或删除(remove)事件"
            },
            "title": {
                "type": "string",
                "description": "事件标题"
            },
            "date": {
                "type": "string",
                "description": "事件日期，格式为YYYY-MM-DD"
            },
            "time": {
                "type": "string",
                "description": "事件时间，格式为HH:MM，24小时制"
            },
            "duration": {
                "type": "integer",
                "description": "事件持续时间（分钟）"
            },
            "description": {
                "type": "string",
                "description": "事件描述"
            },
            "event_id": {
                "type": "string",
                "description": "事件ID，用于删除操作"
            },
            "days": {
                "type": "integer",
                "description": "查询未来几天的事件，默认为7天"
            }
        },
        "required": ["action"],
    }

    def __init__(self):
        """初始化日历工具"""
        # 在实际应用中，可能会从数据库加载事件
        self.events = []
        self._load_events()

    def _load_events(self):
        """从存储中加载事件"""
        try:
            # 在实际应用中，这里应该从数据库加载
            # 这里只是一个示例，使用内存存储
            pass
        except Exception as e:
            logger.error(f"加载事件失败: {str(e)}")
            self.events = []

    def _save_events(self):
        """保存事件到存储"""
        try:
            # 在实际应用中，这里应该保存到数据库
            # 这里只是一个示例，使用内存存储
            pass
        except Exception as e:
            logger.error(f"保存事件失败: {str(e)}")

    def _generate_event_id(self) -> str:
        """生成唯一的事件ID"""
        # 简单使用时间戳作为ID
        return f"evt_{int(datetime.now().timestamp())}"

    def _parse_datetime(self, date_str: str, time_str: Optional[str] = None) -> datetime:
        """解析日期时间字符串

        Args:
            date_str: 日期字符串，格式为YYYY-MM-DD
            time_str: 时间字符串，格式为HH:MM，可选

        Returns:
            datetime: 解析后的日期时间对象
        """
        if time_str:
            return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        return datetime.strptime(date_str, "%Y-%m-%d")

    def _add_event(self, function_args: Dict[str, Any]) -> Dict[str, Any]:
        """添加新事件

        Args:
            function_args: 包含事件信息的参数字典

        Returns:
            Dict: 添加结果
        """
        try:
            title = function_args.get("title")
            date_str = function_args.get("date")
            time_str = function_args.get("time")
            duration = function_args.get("duration", 60)  # 默认1小时
            description = function_args.get("description", "")

            if not title or not date_str:
                return {"status": "error", "message": "缺少必要参数：title和date"}

            # 解析日期时间
            try:
                event_time = self._parse_datetime(date_str, time_str)
            except ValueError:
                return {"status": "error", "message": "日期或时间格式错误"}

            # 创建事件
            event_id = self._generate_event_id()
            event = {
                "id": event_id,
                "title": title,
                "datetime": event_time,
                "duration": duration,
                "description": description,
                "created_at": datetime.now()
            }

            # 添加事件
            self.events.append(event)
            self._save_events()

            return {
                "status": "success",
                "message": f"已成功添加事件：{title}",
                "event_id": event_id
            }
        except Exception as e:
            logger.error(f"添加事件失败: {str(e)}")
            return {"status": "error", "message": f"添加事件失败: {str(e)}"}

    def _check_events(self, function_args: Dict[str, Any]) -> Dict[str, Any]:
        """查询事件

        Args:
            function_args: 包含查询条件的参数字典

        Returns:
            Dict: 查询结果
        """
        try:
            days = function_args.get("days", 7)  # 默认查询未来7天
            date_str = function_args.get("date")
            
            # 如果指定了日期，只查询该日期的事件
            if date_str:
                try:
                    target_date = datetime.strptime(date_str, "%Y-%m-%d")
                    next_date = target_date + timedelta(days=1)
                    
                    filtered_events = [
                        event for event in self.events
                        if target_date <= event["datetime"] < next_date
                    ]
                except ValueError:
                    return {"status": "error", "message": "日期格式错误"}
            else:
                # 查询从今天开始的未来几天的事件
                today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = today + timedelta(days=days)
                
                filtered_events = [
                    event for event in self.events
                    if today <= event["datetime"] < end_date
                ]
            
            # 格式化事件列表
            formatted_events = []
            for event in filtered_events:
                formatted_events.append({
                    "id": event["id"],
                    "title": event["title"],
                    "date": event["datetime"].strftime("%Y-%m-%d"),
                    "time": event["datetime"].strftime("%H:%M"),
                    "duration": event["duration"],
                    "description": event["description"]
                })
            
            # 按日期和时间排序
            formatted_events.sort(key=lambda e: e["date"] + e["time"])
            
            if formatted_events:
                return {
                    "status": "success",
                    "events": formatted_events,
                    "count": len(formatted_events)
                }
            else:
                return {"status": "success", "message": "没有找到符合条件的事件", "count": 0}
        except Exception as e:
            logger.error(f"查询事件失败: {str(e)}")
            return {"status": "error", "message": f"查询事件失败: {str(e)}"}

    def _remove_event(self, function_args: Dict[str, Any]) -> Dict[str, Any]:
        """删除事件

        Args:
            function_args: 包含事件ID的参数字典

        Returns:
            Dict: 删除结果
        """
        try:
            event_id = function_args.get("event_id")
            if not event_id:
                return {"status": "error", "message": "缺少必要参数：event_id"}
            
            # 查找事件
            for i, event in enumerate(self.events):
                if event["id"] == event_id:
                    # 删除事件
                    removed_event = self.events.pop(i)
                    self._save_events()
                    return {
                        "status": "success",
                        "message": f"已成功删除事件：{removed_event['title']}"
                    }
            
            return {"status": "error", "message": f"未找到ID为{event_id}的事件"}
        except Exception as e:
            logger.error(f"删除事件失败: {str(e)}")
            return {"status": "error", "message": f"删除事件失败: {str(e)}"}

    async def execute(self, function_args: Dict[str, Any], message_txt: str = "") -> Dict[str, Any]:
        """执行日历工具操作

        Args:
            function_args: 工具参数
            message_txt: 原始消息文本

        Returns:
            Dict: 工具执行结果
        """
        try:
            action = function_args.get("action")
            
            if action == "add":
                result = self._add_event(function_args)
            elif action == "check":
                result = self._check_events(function_args)
            elif action == "remove":
                result = self._remove_event(function_args)
            else:
                result = {"status": "error", "message": f"未知操作：{action}"}
            
            # 格式化响应内容
            if result.get("status") == "success":
                if "events" in result:
                    # 格式化事件列表显示
                    events_text = []
                    for event in result["events"]:
                        event_text = f"事件：{event['title']}\n"
                        event_text += f"- 时间：{event['date']} {event['time']}\n"
                        event_text += f"- 持续时间：{event['duration']}分钟\n"
                        if event['description']:
                            event_text += f"- 描述：{event['description']}\n"
                        event_text += f"- ID：{event['id']}\n"
                        events_text.append(event_text)
                    
                    content = f"找到{result['count']}个事件：\n\n" + "\n".join(events_text)
                else:
                    content = result.get("message", "操作成功")
            else:
                content = result.get("message", "操作失败")
            
            return {"name": self.name, "content": content}
        except Exception as e:
            logger.error(f"日历工具执行失败: {str(e)}")
            return {"name": self.name, "content": f"日历工具执行失败: {str(e)}"}


# 注册工具
register_tool(CalendarTool) 