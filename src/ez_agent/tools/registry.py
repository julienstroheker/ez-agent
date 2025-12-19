"""Tool registry for managing and executing tools."""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable

from ez_agent.config.models import ToolConfig, ToolType
from ez_agent.tools.base import FunctionTool, ITool, ToolDefinition, ToolError

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry for managing tools.

    Supports:
    - Function tools (Python functions)
    - HTTP tools (API calls)
    - MCP tools (Model Context Protocol servers)
    - A2A tools (Agent-to-Agent protocol)
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._tools: dict[str, ITool] = {}
        self._mcp_tools: list[ToolConfig] = []  # Store MCP tool configs separately
        self._a2a_tools: list[ToolConfig] = []  # Store A2A (agent) tool configs separately

    def register(self, tool: ITool) -> None:
        """
        Register a tool.

        Args:
            tool: Tool instance to register.

        Raises:
            ValueError: If a tool with the same name already exists.
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")

        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def register_function(
        self,
        func: Callable[..., Any],
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        """
        Register a function as a tool.

        Args:
            func: Function to register.
            name: Optional custom name.
            description: Optional custom description.
        """
        # Check if function has @tool decorator metadata
        metadata = getattr(func, "_tool_metadata", {})
        tool_name = name or metadata.get("name")
        tool_desc = description or metadata.get("description")

        tool = FunctionTool(func, name=tool_name, description=tool_desc)
        self.register(tool)

    def register_from_config(self, config: ToolConfig) -> None:
        """
        Register a tool from configuration.

        Args:
            config: Tool configuration.

        Raises:
            ValueError: If tool type is not supported or configuration is invalid.
        """
        if config.type == ToolType.FUNCTION:
            self._register_function_from_config(config)
        elif config.type == ToolType.HTTP:
            self._register_http_from_config(config)
        elif config.type == ToolType.MCP:
            self._register_mcp_from_config(config)
        elif config.type == ToolType.AGENT:
            self._register_a2a_from_config(config)
        else:
            raise ValueError(f"Unsupported tool type: {config.type}")

    def _register_function_from_config(self, config: ToolConfig) -> None:
        """Register a function tool from configuration."""
        if not config.module or not config.function:
            raise ValueError("Function tools require 'module' and 'function' fields")

        try:
            module = importlib.import_module(config.module)
            func = getattr(module, config.function)
        except ImportError as e:
            raise ValueError(f"Could not import module '{config.module}': {e}") from e
        except AttributeError as e:
            raise ValueError(
                f"Function '{config.function}' not found in module '{config.module}': {e}"
            ) from e

        self.register_function(
            func,
            name=config.name,
            description=config.description,
        )

    def _register_http_from_config(self, config: ToolConfig) -> None:
        """Register an HTTP tool from configuration."""
        from ez_agent.tools.builtin.http import HttpTool

        tool = HttpTool(
            name=config.name,
            description=config.description or f"HTTP call to {config.endpoint}",
            endpoint=config.endpoint or "",
            method=config.method,
            headers=config.headers,
        )
        self.register(tool)

    def _register_mcp_from_config(self, config: ToolConfig) -> None:
        """Register MCP tools from configuration."""
        # MCP tools are handled differently - they're passed to the provider
        # which uses the Azure AI Agents SDK's McpTool class
        self._mcp_tools.append(config)
        logger.info(f"Registered MCP tool: {config.name} -> {config.server_url}")

    def _register_a2a_from_config(self, config: ToolConfig) -> None:
        """Register A2A (agent-to-agent) tools from configuration."""
        # A2A tools are handled differently - they're passed to the provider
        # which uses the Azure AI Agents SDK's A2ATool class
        self._a2a_tools.append(config)
        endpoint = config.agent_endpoint or f"project:{config.project_connection_id}"
        logger.info(f"Registered A2A tool: {config.name} -> {endpoint}")

    def get_mcp_tool_configs(self) -> list[ToolConfig]:
        """Get all registered MCP tool configurations."""
        return self._mcp_tools

    def get_a2a_tool_configs(self) -> list[ToolConfig]:
        """Get all registered A2A (agent) tool configurations."""
        return self._a2a_tools

    def get(self, name: str) -> ITool | None:
        """
        Get a tool by name.

        Args:
            name: Tool name.

        Returns:
            Tool instance or None if not found.
        """
        return self._tools.get(name)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """
        Get all tool definitions in JSON schema format.

        Returns:
            List of tool definition dictionaries for LLM consumption.
            Includes function tools, MCP tool configurations, and A2A tools.
        """
        definitions = [tool.get_definition().to_json_schema() for tool in self._tools.values()]
        
        # Add MCP tool definitions with type: mcp
        for mcp_config in self._mcp_tools:
            definitions.append({
                "type": "mcp",
                "name": mcp_config.name,
                "description": mcp_config.description,
                "server_url": mcp_config.server_url,
                "server_label": mcp_config.server_label,
                "allowed_tools": mcp_config.allowed_tools,
                "require_approval": mcp_config.require_approval.value if mcp_config.require_approval else "never",
                "headers": mcp_config.headers,
            })
        
        # Add A2A tool definitions with type: agent
        for a2a_config in self._a2a_tools:
            definitions.append({
                "type": "agent",
                "name": a2a_config.name,
                "description": a2a_config.description,
                "agent_endpoint": a2a_config.agent_endpoint,
                "project_connection_id": a2a_config.project_connection_id,
            })
        
        return definitions

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """
        Execute a tool by name.

        Args:
            name: Tool name.
            arguments: Tool arguments.

        Returns:
            Tool result as string.

        Raises:
            ToolError: If tool not found or execution fails.
        """
        tool = self._tools.get(name)
        if not tool:
            raise ToolError(
                message=f"Tool '{name}' not found",
                tool_name=name,
            )

        return await tool.execute(**arguments)

    def list_tools(self) -> list[str]:
        """Get list of registered tool names."""
        return list(self._tools.keys())

    def clear(self) -> None:
        """Clear all registered tools including MCP and A2A tools."""
        self._tools.clear()
        self._mcp_tools.clear()
        self._a2a_tools.clear()

    def __len__(self) -> int:
        """Return number of registered tools (function + MCP + A2A)."""
        return len(self._tools) + len(self._mcp_tools) + len(self._a2a_tools)

    def __contains__(self, name: str) -> bool:
        """Check if a tool is registered (function, MCP, or A2A)."""
        if name in self._tools:
            return True
        if any(t.server_label == name for t in self._mcp_tools):
            return True
        return any(t.name == name for t in self._a2a_tools)
