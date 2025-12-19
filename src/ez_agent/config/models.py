"""Pydantic models for agent configuration."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProviderType(str, Enum):
    """Supported LLM provider types."""

    AZURE_FOUNDRY = "azure_foundry"
    LOCAL = "local"


class AuthMethod(str, Enum):
    """Authentication methods for providers."""

    DEFAULT_CREDENTIAL = "default_credential"
    API_KEY = "api_key"
    MANAGED_IDENTITY = "managed_identity"


class LogLevel(str, Enum):
    """Logging levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormat(str, Enum):
    """Logging output formats."""

    JSON = "json"
    CONSOLE = "console"


class AuthType(str, Enum):
    """HTTP authentication types for the agent server."""

    NONE = "none"
    BEARER = "bearer"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"


class ToolType(str, Enum):
    """Types of tools available."""

    FUNCTION = "function"
    HTTP = "http"
    MCP = "mcp"
    AGENT = "agent"  # Agent-to-Agent (A2A) tool for invoking other agents


class TracingConfig(BaseModel):
    """Tracing configuration for Azure AI Foundry."""

    enabled: bool = Field(
        default=False,
        description="Enable OpenTelemetry tracing for agent operations.",
    )
    application_insights_connection_string: str | None = Field(
        default=None,
        description="Azure Application Insights connection string. If not provided and enabled, traces will be sent to console.",
    )
    console_tracing: bool = Field(
        default=False,
        description="Also output traces to console (in addition to Application Insights). Useful for local debugging.",
    )
    capture_message_content: bool = Field(
        default=False,
        description="Capture message content in traces. Warning: may contain sensitive data.",
    )
    service_name: str | None = Field(
        default=None,
        description="Service name for traces. Useful for filtering when multiple apps send to same Application Insights.",
    )


class AzureConfig(BaseModel):
    """Azure AI Foundry specific configuration."""

    endpoint: str = Field(
        ...,
        description="Azure AI Foundry endpoint URL",
        examples=["https://my-project.azure.com"],
    )
    auth_method: AuthMethod = Field(
        default=AuthMethod.DEFAULT_CREDENTIAL,
        description="Authentication method to use",
    )
    api_key: str | None = Field(
        default=None,
        description="API key if auth_method is api_key",
    )
    deployment_name: str | None = Field(
        default=None,
        description="Specific deployment name to use",
    )
    persist_agent: bool = Field(
        default=False,
        description="Keep the agent in Azure Foundry when the app is closed. If False (default), the agent is deleted on app shutdown.",
    )
    tracing: TracingConfig = Field(
        default_factory=TracingConfig,
        description="OpenTelemetry tracing configuration for observability.",
    )

    @model_validator(mode="after")
    def validate_api_key_required(self) -> "AzureConfig":
        """Ensure API key is provided when auth method is api_key."""
        if self.auth_method == AuthMethod.API_KEY and not self.api_key:
            raise ValueError("api_key is required when auth_method is 'api_key'")
        return self


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: LogLevel = Field(default=LogLevel.INFO, description="Log level")
    format: LogFormat = Field(default=LogFormat.CONSOLE, description="Log output format")


class AuthConfig(BaseModel):
    """Authentication configuration for the agent HTTP server."""

    enabled: bool = Field(default=False, description="Enable authentication")
    type: AuthType = Field(default=AuthType.BEARER, description="Authentication type")
    secret: str | None = Field(default=None, description="Secret/key for authentication")


class ConfigurationSettings(BaseModel):
    """Runtime configuration settings."""

    provider: ProviderType = Field(
        default=ProviderType.AZURE_FOUNDRY,
        description="LLM provider to use",
    )
    azure: AzureConfig | None = Field(
        default=None,
        description="Azure AI Foundry configuration",
    )
    logging: LoggingConfig = Field(
        default_factory=LoggingConfig,
        description="Logging configuration",
    )
    auth: AuthConfig = Field(
        default_factory=AuthConfig,
        description="HTTP server authentication",
    )
    a2a_enabled: bool = Field(
        default=True,
        description="Enable A2A protocol support",
    )

    @model_validator(mode="after")
    def validate_provider_config(self) -> "ConfigurationSettings":
        """Ensure provider-specific config is present."""
        if self.provider == ProviderType.AZURE_FOUNDRY and not self.azure:
            raise ValueError("azure configuration is required when provider is 'azure_foundry'")
        return self


class FeatureFlags(BaseModel):
    """Feature flags for enabling/disabling features."""

    model_config = ConfigDict(extra="allow")  # Allow additional feature flags

    streaming: bool = Field(default=True, description="Enable streaming responses")
    tool_execution: bool = Field(default=True, description="Enable tool execution")
    conversation_history: bool = Field(default=True, description="Maintain conversation history")


class MCPApprovalMode(str, Enum):
    """MCP tool approval modes."""

    ALWAYS = "always"  # Always require approval for tool calls (default)
    NEVER = "never"  # Never require approval


class ToolConfig(BaseModel):
    """Configuration for a tool."""

    name: str = Field(..., description="Tool name", min_length=1, max_length=64)
    type: ToolType = Field(..., description="Tool type")
    description: str | None = Field(default=None, description="Tool description")

    # For function tools
    module: str | None = Field(default=None, description="Python module path")
    function: str | None = Field(default=None, description="Function name in module")

    # For HTTP tools
    endpoint: str | None = Field(default=None, description="HTTP endpoint URL")
    method: str = Field(default="POST", description="HTTP method")
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP headers")

    # For MCP tools (HTTP-based Model Context Protocol servers)
    server_url: str | None = Field(
        default=None,
        description="MCP server URL (e.g., https://gitmcp.io/Azure/azure-rest-api-specs)",
    )
    server_label: str | None = Field(
        default=None,
        description="Unique label for this MCP server. Must be alphanumeric with underscores only.",
    )
    allowed_tools: list[str] | None = Field(
        default=None,
        description="List of specific tools to allow from this MCP server. If None, all tools are allowed.",
    )
    require_approval: MCPApprovalMode = Field(
        default=MCPApprovalMode.NEVER,
        description="Whether to require user approval for MCP tool calls. Default is 'never' for non-interactive use.",
    )

    # For Agent (A2A) tools - Agent-to-Agent communication
    agent_endpoint: str | None = Field(
        default=None,
        description="A2A agent endpoint URL (e.g., https://my-agent.example.com/.well-known/a2a)",
    )
    project_connection_id: str | None = Field(
        default=None,
        description="Azure AI Project connection ID for A2A tools. Use this for agents within the same project.",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure tool name is a valid identifier."""
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", v):
            raise ValueError("Tool name must be a valid Python identifier")
        return v

    @field_validator("server_label")
    @classmethod
    def validate_server_label(cls, v: str | None) -> str | None:
        """Ensure server_label matches Azure requirements: alphanumeric and underscores only."""
        if v is not None and not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("server_label must be alphanumeric with underscores only (pattern: ^[a-zA-Z0-9_]+$)")
        return v

    @model_validator(mode="after")
    def validate_tool_type_fields(self) -> "ToolConfig":
        """Validate that required fields are present for each tool type."""
        if self.type == ToolType.FUNCTION:
            if not self.module or not self.function:
                raise ValueError("module and function are required for function tools")
        elif self.type == ToolType.HTTP:
            if not self.endpoint:
                raise ValueError("endpoint is required for HTTP tools")
        elif self.type == ToolType.MCP:
            if not self.server_url:
                raise ValueError("server_url is required for MCP tools")
            # Auto-generate server_label from name if not provided
            if not self.server_label:
                # Convert name to valid server_label format
                self.server_label = re.sub(r"[^a-zA-Z0-9_]", "_", self.name)
        elif self.type == ToolType.AGENT:
            # Agent tools require either an endpoint URL or a project connection ID
            if not self.agent_endpoint and not self.project_connection_id:
                raise ValueError("agent_endpoint or project_connection_id is required for agent (A2A) tools")
        return self


class AgentConfig(BaseModel):
    """Main agent configuration model."""

    name: str = Field(
        ...,
        description="Agent name",
        min_length=1,
        max_length=64,
        examples=["MyBot"],
    )
    description: str = Field(
        ...,
        description="Agent description",
        min_length=1,
        max_length=500,
    )
    version: str = Field(
        ...,
        description="Semantic version",
        pattern=r"^\d+\.\d+\.\d+.*$",
        examples=["1.0.0"],
    )
    instructions: str = Field(
        ...,
        description="System instructions for the agent",
        min_length=1,
    )
    model: str = Field(
        ...,
        description="Model identifier to use",
        examples=["gpt-4o", "gpt-4o-mini"],
    )
    configuration: ConfigurationSettings = Field(
        default_factory=ConfigurationSettings,
        description="Runtime configuration settings",
    )
    features: FeatureFlags = Field(
        default_factory=FeatureFlags,
        description="Feature flags",
    )
    tools: list[ToolConfig] = Field(
        default_factory=list,
        description="Tool configurations",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure agent name is URL-safe."""
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*$", v):
            raise ValueError("Agent name must start with a letter and contain only alphanumeric characters, underscores, and hyphens")
        return v

    def get_feature(self, name: str, default: bool = False) -> bool:
        """Get a feature flag value."""
        return getattr(self.features, name, default)

    def model_post_init(self, __context: Any) -> None:
        """Post-initialization validation."""
        # Ensure tool names are unique
        tool_names = [tool.name for tool in self.tools]
        if len(tool_names) != len(set(tool_names)):
            raise ValueError("Tool names must be unique")
