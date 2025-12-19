"""Base provider interface and types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator


class MessageRole(str, Enum):
    """Message roles in a conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ToolCall:
    """Represents a tool call requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    """Represents the result of a tool execution."""

    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class ProviderMessage:
    """A message in a conversation."""

    role: MessageRole
    content: str
    name: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None

    @classmethod
    def system(cls, content: str) -> "ProviderMessage":
        """Create a system message."""
        return cls(role=MessageRole.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str) -> "ProviderMessage":
        """Create a user message."""
        return cls(role=MessageRole.USER, content=content)

    @classmethod
    def assistant(
        cls, content: str, tool_calls: list[ToolCall] | None = None
    ) -> "ProviderMessage":
        """Create an assistant message."""
        return cls(
            role=MessageRole.ASSISTANT,
            content=content,
            tool_calls=tool_calls or [],
        )

    @classmethod
    def tool_result(cls, tool_call_id: str, content: str, is_error: bool = False) -> "ProviderMessage":
        """Create a tool result message."""
        return cls(
            role=MessageRole.TOOL,
            content=content,
            tool_call_id=tool_call_id,
        )


@dataclass
class ProviderResponse:
    """Response from a provider completion call."""

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)

    @property
    def requires_action(self) -> bool:
        """Check if the response requires tool execution."""
        return bool(self.tool_calls) and len(self.tool_calls) > 0


@dataclass
class StreamChunk:
    """A chunk of a streaming response."""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    is_final: bool = False


class IProvider(ABC):
    """
    Abstract base class for LLM providers.

    Implementations must support both synchronous and streaming completions,
    as well as tool/function calling.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider name."""
        ...

    @abstractmethod
    async def complete(
        self,
        messages: list[ProviderMessage],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ProviderResponse:
        """
        Generate a completion for the given messages.

        Args:
            messages: List of conversation messages.
            model: Model identifier to use.
            tools: Optional list of tool definitions (JSON schema format).
            temperature: Sampling temperature (0.0-2.0).
            max_tokens: Maximum tokens to generate.

        Returns:
            ProviderResponse with content and optional tool calls.

        Raises:
            ProviderError: If the completion fails.
        """
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[ProviderMessage],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Generate a streaming completion for the given messages.

        Args:
            messages: List of conversation messages.
            model: Model identifier to use.
            tools: Optional list of tool definitions.
            temperature: Sampling temperature (0.0-2.0).
            max_tokens: Maximum tokens to generate.

        Yields:
            StreamChunk objects with incremental content.

        Raises:
            ProviderError: If the completion fails.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the provider is healthy and accessible.

        Returns:
            True if healthy, False otherwise.
        """
        ...

    def set_agent_name(self, name: str) -> None:
        """
        Set the agent name for providers that support named agents.
        
        This is called by the factory after provider creation to pass
        the agent name from configuration.
        
        Args:
            name: The agent name from the YAML configuration.
        """
        pass  # Default implementation does nothing

    def set_instructions(self, instructions: str) -> None:
        """
        Set the agent instructions for providers that support them.
        
        This is called by the factory after provider creation to pass
        the instructions from configuration.
        
        Args:
            instructions: The system instructions for the agent.
        """
        pass  # Default implementation does nothing

    async def close(self) -> None:
        """Clean up any resources (optional override)."""
        pass


class ProviderError(Exception):
    """Base exception for provider errors."""

    def __init__(self, message: str, provider: str, cause: Exception | None = None):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.cause = cause


class ProviderAuthError(ProviderError):
    """Authentication or authorization error."""

    pass


class ProviderRateLimitError(ProviderError):
    """Rate limit exceeded error."""

    def __init__(
        self,
        message: str,
        provider: str,
        retry_after: float | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, provider, cause)
        self.retry_after = retry_after


class ProviderModelError(ProviderError):
    """Model not found or not available error."""

    pass
