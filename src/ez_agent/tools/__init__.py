"""Tool system for the agent."""

from ez_agent.tools.base import ITool, ToolError, tool
from ez_agent.tools.registry import ToolRegistry
from ez_agent.tools.executor import ToolExecutor

__all__ = [
    "ITool",
    "ToolError",
    "tool",
    "ToolRegistry",
    "ToolExecutor",
]
