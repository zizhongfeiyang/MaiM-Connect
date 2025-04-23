"""Maim Message - A message handling library"""

__version__ = "0.1.0"

from .api import MessageClient, MessageServer
from .router import Router, RouteConfig, TargetConfig
from .message_base import (
    Seg,
    GroupInfo,
    UserInfo,
    FormatInfo,
    TemplateInfo,
    BaseMessageInfo,
    MessageBase,
)

__all__ = [
    "MessageClient",
    "MessageServer",
    "Router",
    "RouteConfig",
    "TargetConfig",
    "Seg",
    "GroupInfo",
    "UserInfo",
    "FormatInfo",
    "TemplateInfo",
    "BaseMessageInfo",
    "MessageBase",
]
