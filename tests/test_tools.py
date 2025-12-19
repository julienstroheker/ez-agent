"""Tests for the tool system."""

from __future__ import annotations

import json

import pytest

from ez_agent.config.models import MCPApprovalMode, ToolConfig, ToolType
from ez_agent.tools.base import FunctionTool, ToolError, tool
from ez_agent.tools.registry import ToolRegistry


class TestToolDecorator:
    """Test the @tool decorator."""

    def test_tool_decorator_stores_metadata(self):
        """Test that decorator stores metadata on function."""
        @tool(name="custom_name", description="Custom description")
        def my_func():
            pass

        assert hasattr(my_func, "_tool_metadata")
        assert my_func._tool_metadata["name"] == "custom_name"
        assert my_func._tool_metadata["description"] == "Custom description"

    def test_tool_decorator_without_args(self):
        """Test decorator without arguments."""
        @tool()
        def my_func():
            pass

        assert hasattr(my_func, "_tool_metadata")
        assert my_func._tool_metadata["name"] is None


class TestFunctionTool:
    """Test FunctionTool wrapper."""

    def test_extracts_name_from_function(self):
        """Test that tool name comes from function name."""
        def get_weather():
            pass

        tool = FunctionTool(get_weather)
        assert tool.name == "get_weather"

    def test_extracts_description_from_docstring(self):
        """Test that description comes from docstring."""
        def get_weather():
            """Get the current weather."""
            pass

        tool = FunctionTool(get_weather)
        assert "weather" in tool.description.lower()

    def test_custom_name_overrides(self):
        """Test that custom name overrides function name."""
        def get_weather():
            pass

        tool = FunctionTool(get_weather, name="fetch_weather")
        assert tool.name == "fetch_weather"

    def test_generates_parameter_schema(self):
        """Test that parameters are extracted from type hints."""
        def get_weather(city: str, units: str = "celsius") -> str:
            """Get weather.

            Args:
                city: The city name.
                units: Temperature units.
            """
            return ""

        tool = FunctionTool(get_weather)
        definition = tool.get_definition()

        assert len(definition.parameters) == 2

        city_param = next(p for p in definition.parameters if p.name == "city")
        assert city_param.type == "string"
        assert city_param.required is True

        units_param = next(p for p in definition.parameters if p.name == "units")
        assert units_param.required is False

    async def test_execute_sync_function(self):
        """Test executing a synchronous function."""
        def add(a: int, b: int) -> int:
            return a + b

        tool = FunctionTool(add)
        result = await tool.execute(a=2, b=3)

        assert result == "5"

    async def test_execute_async_function(self):
        """Test executing an async function."""
        async def async_add(a: int, b: int) -> int:
            return a + b

        tool = FunctionTool(async_add)
        result = await tool.execute(a=2, b=3)

        assert result == "5"

    async def test_execute_returns_json(self):
        """Test that dict results are JSON-encoded."""
        def get_data() -> dict:
            return {"key": "value"}

        tool = FunctionTool(get_data)
        result = await tool.execute()

        parsed = json.loads(result)
        assert parsed == {"key": "value"}

    async def test_execute_error_raises_tool_error(self):
        """Test that execution errors raise ToolError."""
        def failing_func():
            raise ValueError("Something went wrong")

        tool = FunctionTool(failing_func)

        with pytest.raises(ToolError) as exc_info:
            await tool.execute()

        assert "Something went wrong" in str(exc_info.value)


class TestToolRegistry:
    """Test ToolRegistry."""

    @pytest.fixture
    def registry(self) -> ToolRegistry:
        return ToolRegistry()

    def test_register_tool(self, registry: ToolRegistry):
        """Test registering a tool."""
        def my_tool():
            pass

        tool = FunctionTool(my_tool)
        registry.register(tool)

        assert "my_tool" in registry
        assert len(registry) == 1

    def test_register_duplicate_raises(self, registry: ToolRegistry):
        """Test that registering duplicate raises error."""
        def my_tool():
            pass

        tool = FunctionTool(my_tool)
        registry.register(tool)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(tool)

    def test_register_function(self, registry: ToolRegistry):
        """Test registering a function directly."""
        def my_tool():
            pass

        registry.register_function(my_tool)
        assert "my_tool" in registry

    def test_register_decorated_function(self, registry: ToolRegistry):
        """Test registering a decorated function."""
        @tool(name="custom_tool")
        def my_func():
            pass

        registry.register_function(my_func)
        assert "custom_tool" in registry

    def test_get_tool_definitions(self, registry: ToolRegistry):
        """Test getting tool definitions for LLM."""
        def tool1(x: str) -> str:
            """Tool one."""
            return x

        def tool2(y: int) -> int:
            """Tool two."""
            return y

        registry.register_function(tool1)
        registry.register_function(tool2)

        definitions = registry.get_tool_definitions()

        assert len(definitions) == 2
        assert all("name" in d for d in definitions)
        assert all("parameters" in d for d in definitions)

    async def test_execute_tool(self, registry: ToolRegistry):
        """Test executing a tool by name."""
        def add(a: int, b: int) -> int:
            return a + b

        registry.register_function(add)
        result = await registry.execute("add", {"a": 2, "b": 3})

        assert result == "5"

    async def test_execute_nonexistent_raises(self, registry: ToolRegistry):
        """Test that executing nonexistent tool raises error."""
        with pytest.raises(ToolError, match="not found"):
            await registry.execute("nonexistent", {})

    def test_list_tools(self, registry: ToolRegistry):
        """Test listing registered tools."""
        registry.register_function(lambda: None, name="tool1")
        registry.register_function(lambda: None, name="tool2")

        tools = registry.list_tools()
        assert set(tools) == {"tool1", "tool2"}

    def test_clear(self, registry: ToolRegistry):
        """Test clearing registry."""
        registry.register_function(lambda: None, name="tool1")
        registry.clear()

        assert len(registry) == 0


class TestMCPToolRegistry:
    """Test MCP tool handling in ToolRegistry."""

    @pytest.fixture
    def registry(self) -> ToolRegistry:
        return ToolRegistry()

    def test_register_mcp_from_config(self, registry: ToolRegistry):
        """Test registering an MCP tool from config."""
        config = ToolConfig(
            name="my_mcp",
            type=ToolType.MCP,
            server_url="https://mcp.example.com",
            description="MCP server",
        )
        registry.register_from_config(config)

        # MCP tools should be stored separately
        mcp_configs = registry.get_mcp_tool_configs()
        assert len(mcp_configs) == 1
        assert mcp_configs[0].name == "my_mcp"

    def test_get_mcp_tool_configs_empty(self, registry: ToolRegistry):
        """Test get_mcp_tool_configs returns empty list when none registered."""
        assert registry.get_mcp_tool_configs() == []

    def test_mcp_tools_included_in_registry(self, registry: ToolRegistry):
        """Test that MCP tools are included in registry len and contains."""
        config = ToolConfig(
            name="my_mcp",
            type=ToolType.MCP,
            server_url="https://mcp.example.com",
            description="MCP server",
        )
        registry.register_from_config(config)

        # MCP tools should be counted and findable
        assert "my_mcp" in registry
        assert len(registry) == 1

    def test_get_tool_definitions_includes_mcp(self, registry: ToolRegistry):
        """Test that get_tool_definitions includes MCP tools."""
        # Register a function tool
        def my_func() -> str:
            """A function."""
            return "result"
        registry.register_function(my_func)

        # Register an MCP tool
        mcp_config = ToolConfig(
            name="my_mcp",
            type=ToolType.MCP,
            server_url="https://mcp.example.com",
            server_label="my_mcp_label",
            allowed_tools=["tool1", "tool2"],
            require_approval=MCPApprovalMode.ALWAYS,
            description="MCP server",
        )
        registry.register_from_config(mcp_config)

        definitions = registry.get_tool_definitions()
        assert len(definitions) == 2

        # Find the MCP definition
        mcp_def = next((d for d in definitions if d.get("type") == "mcp"), None)
        assert mcp_def is not None
        assert mcp_def["name"] == "my_mcp"
        assert mcp_def["server_url"] == "https://mcp.example.com"
        assert mcp_def["server_label"] == "my_mcp_label"
        assert mcp_def["allowed_tools"] == ["tool1", "tool2"]
        assert mcp_def["require_approval"] == "always"

    def test_clear_also_clears_mcp_tools(self, registry: ToolRegistry):
        """Test that clear() also clears MCP tools."""
        config = ToolConfig(
            name="my_mcp",
            type=ToolType.MCP,
            server_url="https://mcp.example.com",
            description="MCP server",
        )
        registry.register_from_config(config)
        
        registry.clear()
        
        assert registry.get_mcp_tool_configs() == []

    def test_multiple_mcp_tools(self, registry: ToolRegistry):
        """Test registering multiple MCP tools."""
        for i in range(3):
            config = ToolConfig(
                name=f"mcp_{i}",
                type=ToolType.MCP,
                server_url=f"https://mcp{i}.example.com",
                description=f"MCP server {i}",
            )
            registry.register_from_config(config)

        mcp_configs = registry.get_mcp_tool_configs()
        assert len(mcp_configs) == 3
        names = [c.name for c in mcp_configs]
        assert set(names) == {"mcp_0", "mcp_1", "mcp_2"}


class TestA2AToolRegistry:
    """Tests for A2A (Agent-to-Agent) tool registration in ToolRegistry."""

    @pytest.fixture
    def registry(self) -> ToolRegistry:
        return ToolRegistry()

    def test_register_a2a_tool_with_project_connection(self, registry: ToolRegistry):
        """Test registering an A2A tool with project connection ID."""
        config = ToolConfig(
            name="helper_agent",
            type=ToolType.AGENT,
            description="Helper agent for data analysis",
            project_connection_id="my-project-connection-id",
        )
        registry.register_from_config(config)

        assert len(registry) == 1
        assert "helper_agent" in registry

    def test_register_a2a_tool_with_endpoint(self, registry: ToolRegistry):
        """Test registering an A2A tool with external endpoint."""
        config = ToolConfig(
            name="external_agent",
            type=ToolType.AGENT,
            description="External agent",
            agent_endpoint="https://my-agent.example.com/api/agent",
        )
        registry.register_from_config(config)

        assert len(registry) == 1
        assert "external_agent" in registry

    def test_get_a2a_tool_configs(self, registry: ToolRegistry):
        """Test getting A2A tool configs."""
        config = ToolConfig(
            name="helper_agent",
            type=ToolType.AGENT,
            description="Helper agent",
            project_connection_id="conn-123",
        )
        registry.register_from_config(config)

        a2a_configs = registry.get_a2a_tool_configs()
        assert len(a2a_configs) == 1
        assert a2a_configs[0].name == "helper_agent"
        assert a2a_configs[0].project_connection_id == "conn-123"

    def test_get_a2a_tool_configs_empty(self, registry: ToolRegistry):
        """Test get_a2a_tool_configs returns empty list when none registered."""
        assert registry.get_a2a_tool_configs() == []

    def test_a2a_tools_included_in_registry(self, registry: ToolRegistry):
        """Test that A2A tools are included in registry len and contains."""
        config = ToolConfig(
            name="my_agent",
            type=ToolType.AGENT,
            description="Agent tool",
            project_connection_id="conn-id",
        )
        registry.register_from_config(config)

        assert "my_agent" in registry
        assert len(registry) == 1

    def test_get_tool_definitions_includes_a2a(self, registry: ToolRegistry):
        """Test that get_tool_definitions includes A2A tools."""
        # Register a function tool
        def dummy_fn():
            """A dummy function."""
            pass
        registry.register_function(dummy_fn, name="func_tool", description="A function tool")

        # Register an A2A tool
        a2a_config = ToolConfig(
            name="my_agent",
            type=ToolType.AGENT,
            project_connection_id="conn-123",
            agent_endpoint="https://agent.example.com",
            description="Agent tool",
        )
        registry.register_from_config(a2a_config)

        definitions = registry.get_tool_definitions()
        assert len(definitions) == 2

        # Find the A2A definition
        a2a_def = next((d for d in definitions if d.get("type") == "agent"), None)
        assert a2a_def is not None
        assert a2a_def["name"] == "my_agent"
        assert a2a_def["project_connection_id"] == "conn-123"
        assert a2a_def["agent_endpoint"] == "https://agent.example.com"

    def test_clear_also_clears_a2a_tools(self, registry: ToolRegistry):
        """Test that clear() also clears A2A tools."""
        config = ToolConfig(
            name="my_agent",
            type=ToolType.AGENT,
            project_connection_id="conn-123",
            description="Agent tool",
        )
        registry.register_from_config(config)
        
        registry.clear()
        
        assert registry.get_a2a_tool_configs() == []

    def test_multiple_a2a_tools(self, registry: ToolRegistry):
        """Test registering multiple A2A tools."""
        for i in range(3):
            config = ToolConfig(
                name=f"agent_{i}",
                type=ToolType.AGENT,
                project_connection_id=f"conn-{i}",
                description=f"Agent {i}",
            )
            registry.register_from_config(config)

        a2a_configs = registry.get_a2a_tool_configs()
        assert len(a2a_configs) == 3
        names = [c.name for c in a2a_configs]
        assert set(names) == {"agent_0", "agent_1", "agent_2"}
