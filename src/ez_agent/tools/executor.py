"""Tool executor with error handling and result formatting."""

from __future__ import annotations

import json
import logging
from typing import Any

from ez_agent.tools.base import ToolError
from ez_agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutor:
    """
    High-level tool executor with error handling and logging.

    Wraps the ToolRegistry with additional functionality:
    - Structured error responses
    - Execution logging
    - Result formatting
    """

    def __init__(self, registry: ToolRegistry) -> None:
        """
        Initialize the executor.

        Args:
            registry: Tool registry to use.
        """
        self._registry = registry

    async def execute(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute a tool and return a structured result.

        Args:
            tool_call_id: ID to correlate with tool call.
            tool_name: Name of the tool to execute.
            arguments: Tool arguments.

        Returns:
            Dictionary with tool_call_id and output.
        """
        logger.info(f"Executing tool '{tool_name}' (call_id: {tool_call_id})")
        logger.debug(f"Tool arguments: {arguments}")

        try:
            result = await self._registry.execute(tool_name, arguments)

            logger.debug(f"Tool '{tool_name}' completed successfully")

            return {
                "tool_call_id": tool_call_id,
                "output": result,
            }

        except ToolError as e:
            logger.error(f"Tool '{tool_name}' failed: {e.message}")
            return {
                "tool_call_id": tool_call_id,
                "output": json.dumps({
                    "error": True,
                    "message": e.message,
                    "tool": e.tool_name,
                }),
            }

        except Exception as e:
            logger.exception(f"Unexpected error executing tool '{tool_name}': {e}")
            return {
                "tool_call_id": tool_call_id,
                "output": json.dumps({
                    "error": True,
                    "message": f"Unexpected error: {e}",
                    "tool": tool_name,
                }),
            }

    async def execute_batch(
        self,
        tool_calls: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Execute multiple tool calls.

        Args:
            tool_calls: List of tool calls with id, name, and arguments.

        Returns:
            List of results with tool_call_id and output.
        """
        results = []

        for call in tool_calls:
            result = await self.execute(
                tool_call_id=call["id"],
                tool_name=call["name"],
                arguments=call.get("arguments", {}),
            )
            results.append(result)

        return results
