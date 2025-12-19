"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ez_agent.config import load_config, validate_config, ConfigError
from ez_agent.config.models import (
    AgentConfig,
    AuthMethod,
    MCPApprovalMode,
    ProviderType,
    ToolConfig,
    ToolType,
)


class TestConfigModels:
    """Test configuration model validation."""

    def test_minimal_valid_config(self):
        """Test that minimal required fields work."""
        config = AgentConfig(
            name="TestBot",
            description="A test bot",
            version="1.0.0",
            instructions="Be helpful.",
            model="gpt-4o",
            configuration={"provider": "local"},
        )

        assert config.name == "TestBot"
        assert config.version == "1.0.0"
        assert config.configuration.provider == ProviderType.LOCAL

    def test_invalid_name_rejected(self):
        """Test that invalid agent names are rejected."""
        with pytest.raises(ValueError, match="Agent name must start with a letter"):
            AgentConfig(
                name="123invalid",
                description="Test",
                version="1.0.0",
                instructions="Test",
                model="gpt-4o",
                configuration={"provider": "local"},
            )

    def test_invalid_version_rejected(self):
        """Test that invalid version formats are rejected."""
        with pytest.raises(ValueError):
            AgentConfig(
                name="TestBot",
                description="Test",
                version="invalid",
                instructions="Test",
                model="gpt-4o",
            )

    def test_azure_config_requires_endpoint(self):
        """Test that Azure config requires endpoint."""
        with pytest.raises(ValueError, match="azure configuration is required"):
            AgentConfig(
                name="TestBot",
                description="Test",
                version="1.0.0",
                instructions="Test",
                model="gpt-4o",
                configuration={
                    "provider": "azure_foundry",
                },
            )

    def test_azure_api_key_requires_key(self):
        """Test that API key auth requires the key."""
        from ez_agent.config.models import AzureConfig

        with pytest.raises(ValueError, match="api_key is required"):
            AzureConfig(
                endpoint="https://test.azure.com",
                auth_method=AuthMethod.API_KEY,
            )

    def test_duplicate_tool_names_rejected(self):
        """Test that duplicate tool names are rejected."""
        with pytest.raises(ValueError, match="Tool names must be unique"):
            AgentConfig(
                name="TestBot",
                description="Test",
                version="1.0.0",
                instructions="Test",
                model="gpt-4o",
                configuration={"provider": "local"},
                tools=[
                    {"name": "my_tool", "type": "function", "module": "x", "function": "y"},
                    {"name": "my_tool", "type": "function", "module": "a", "function": "b"},
                ],
            )


class TestMCPToolConfig:
    """Test MCP tool configuration validation."""

    def test_mcp_tool_requires_server_url(self):
        """Test that MCP tools require server_url."""
        with pytest.raises(ValueError, match="server_url is required for MCP tools"):
            ToolConfig(
                name="my_mcp_tool",
                type=ToolType.MCP,
                description="An MCP tool",
            )

    def test_mcp_tool_auto_generates_server_label(self):
        """Test that server_label is auto-generated from name."""
        config = ToolConfig(
            name="my_mcp_tool",
            type=ToolType.MCP,
            server_url="https://mcp.example.com",
            description="An MCP tool",
        )
        # Name should be used directly as server_label
        assert config.server_label == "my_mcp_tool"

    def test_mcp_tool_explicit_server_label(self):
        """Test that explicit server_label is used."""
        config = ToolConfig(
            name="my_mcp_tool",
            type=ToolType.MCP,
            server_url="https://mcp.example.com",
            server_label="custom_label",
            description="An MCP tool",
        )
        assert config.server_label == "custom_label"

    def test_mcp_tool_invalid_server_label_rejected(self):
        """Test that invalid server_label patterns are rejected."""
        with pytest.raises(ValueError, match="server_label must be alphanumeric"):
            ToolConfig(
                name="my_mcp_tool",
                type=ToolType.MCP,
                server_url="https://mcp.example.com",
                server_label="invalid-label",  # Hyphens not allowed
                description="An MCP tool",
            )

    def test_mcp_tool_approval_mode_always(self):
        """Test MCP tool with approval mode 'always'."""
        config = ToolConfig(
            name="secure_tool",
            type=ToolType.MCP,
            server_url="https://mcp.example.com",
            require_approval=MCPApprovalMode.ALWAYS,
            description="Secure tool",
        )
        assert config.require_approval == MCPApprovalMode.ALWAYS

    def test_mcp_tool_approval_mode_never_default(self):
        """Test MCP tool approval mode defaults to 'never'."""
        config = ToolConfig(
            name="tool",
            type=ToolType.MCP,
            server_url="https://mcp.example.com",
            description="Tool",
        )
        assert config.require_approval == MCPApprovalMode.NEVER

    def test_mcp_tool_with_allowed_tools(self):
        """Test MCP tool with specific allowed tools."""
        config = ToolConfig(
            name="limited_mcp",
            type=ToolType.MCP,
            server_url="https://mcp.example.com",
            allowed_tools=["tool1", "tool2"],
            description="Limited MCP",
        )
        assert config.allowed_tools == ["tool1", "tool2"]

    def test_mcp_tool_with_headers(self):
        """Test MCP tool with custom headers."""
        config = ToolConfig(
            name="authed_mcp",
            type=ToolType.MCP,
            server_url="https://mcp.example.com",
            headers={"Authorization": "Bearer token123"},
            description="Authed MCP",
        )
        assert config.headers == {"Authorization": "Bearer token123"}


class TestA2AToolConfig:
    """Tests for A2A (Agent-to-Agent) tool configuration."""

    def test_a2a_tool_with_project_connection(self):
        """Test A2A tool requires project_connection_id or agent_endpoint."""
        config = ToolConfig(
            name="helper",
            type=ToolType.AGENT,
            description="Helper agent",
            project_connection_id="my-connection-id",
        )
        assert config.type == ToolType.AGENT
        assert config.project_connection_id == "my-connection-id"

    def test_a2a_tool_with_agent_endpoint(self):
        """Test A2A tool with external endpoint."""
        config = ToolConfig(
            name="external_agent",
            type=ToolType.AGENT,
            description="External agent",
            agent_endpoint="https://agent.example.com/api",
        )
        assert config.type == ToolType.AGENT
        assert config.agent_endpoint == "https://agent.example.com/api"

    def test_a2a_tool_with_both_connection_and_endpoint(self):
        """Test A2A tool can have both connection ID and endpoint."""
        config = ToolConfig(
            name="hybrid_agent",
            type=ToolType.AGENT,
            description="Hybrid agent",
            project_connection_id="conn-123",
            agent_endpoint="https://fallback.example.com",
        )
        assert config.project_connection_id == "conn-123"
        assert config.agent_endpoint == "https://fallback.example.com"


class TestConfigLoader:
    """Test configuration file loading."""

    def test_load_valid_config(self, tmp_path: Path):
        """Test loading a valid configuration file."""
        config_path = tmp_path / "agent.yaml"
        config_content = """
name: TestAgent
description: A test agent
version: 1.0.0
instructions: Be helpful.
model: gpt-4o
configuration:
  provider: local
"""
        config_path.write_text(config_content)

        config = load_config(config_path)
        assert config.name == "TestAgent"
        assert config.configuration.provider == ProviderType.LOCAL

    def test_load_nonexistent_file(self, tmp_path: Path):
        """Test that loading a nonexistent file raises error."""
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path / "nonexistent.yaml")

    def test_load_invalid_yaml(self, tmp_path: Path):
        """Test that invalid YAML raises error."""
        config_path = tmp_path / "invalid.yaml"
        config_path.write_text("{ invalid yaml [")

        with pytest.raises(ConfigError, match="Invalid YAML"):
            load_config(config_path)

    def test_load_missing_required_fields(self, tmp_path: Path):
        """Test that missing required fields raise error."""
        config_path = tmp_path / "incomplete.yaml"
        config_path.write_text("name: TestAgent\n")

        with pytest.raises(ConfigError, match="validation failed"):
            load_config(config_path)

    def test_environment_variable_expansion(self, tmp_path: Path, monkeypatch):
        """Test that environment variables are expanded."""
        monkeypatch.setenv("TEST_ENDPOINT", "https://test.example.com")

        config_path = tmp_path / "env.yaml"
        config_content = """
name: TestAgent
description: Test
version: 1.0.0
instructions: Test
model: gpt-4o
configuration:
  provider: azure_foundry
  azure:
    endpoint: ${TEST_ENDPOINT}
    auth_method: default_credential
"""
        config_path.write_text(config_content)

        config = load_config(config_path)
        assert config.configuration.azure.endpoint == "https://test.example.com"

    def test_env_var_with_default(self, tmp_path: Path):
        """Test environment variable with default value."""
        config_path = tmp_path / "default.yaml"
        config_content = """
name: TestAgent
description: Test
version: 1.0.0
instructions: Test
model: ${UNDEFINED_VAR:-gpt-4o}
configuration:
  provider: local
"""
        config_path.write_text(config_content)

        config = load_config(config_path)
        assert config.model == "gpt-4o"


class TestConfigValidation:
    """Test configuration validation function."""

    def test_validate_valid_config(self, tmp_path: Path):
        """Test validating a valid configuration."""
        config_path = tmp_path / "valid.yaml"
        config_content = """
name: TestAgent
description: Test
version: 1.0.0
instructions: Test
model: gpt-4o
configuration:
  provider: local
"""
        config_path.write_text(config_content)

        is_valid, errors = validate_config(config_path)
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_invalid_config(self, tmp_path: Path):
        """Test validating an invalid configuration."""
        config_path = tmp_path / "invalid.yaml"
        config_path.write_text("name: 123\n")

        is_valid, errors = validate_config(config_path)
        assert is_valid is False
        assert len(errors) > 0
