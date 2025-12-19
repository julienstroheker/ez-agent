"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator, Any

import pytest

from ez_agent.config.models import (
    AgentConfig,
    AuthMethod,
    AzureConfig,
    ConfigurationSettings,
    FeatureFlags,
    ProviderType,
)
from ez_agent.providers.base import (
    IProvider,
    ProviderMessage,
    ProviderResponse,
    StreamChunk,
)
from ez_agent.storage.memory import InMemoryConversationStore, InMemoryTaskStore


@pytest.fixture
def sample_config() -> AgentConfig:
    """Create a sample agent configuration for testing."""
    return AgentConfig(
        name="TestAgent",
        description="A test agent",
        version="1.0.0",
        instructions="You are a helpful test assistant.",
        model="gpt-4o",
        configuration=ConfigurationSettings(
            provider=ProviderType.LOCAL,
        ),
        features=FeatureFlags(
            streaming=True,
            tool_execution=True,
            conversation_history=True,
        ),
        tools=[],
    )


@pytest.fixture
def azure_config() -> AgentConfig:
    """Create a sample Azure configuration for testing."""
    return AgentConfig(
        name="AzureTestAgent",
        description="A test agent using Azure",
        version="1.0.0",
        instructions="You are a helpful test assistant.",
        model="gpt-4o",
        configuration=ConfigurationSettings(
            provider=ProviderType.AZURE_FOUNDRY,
            azure=AzureConfig(
                endpoint="https://test.azure.com",
                auth_method=AuthMethod.DEFAULT_CREDENTIAL,
            ),
        ),
        features=FeatureFlags(),
        tools=[],
    )


@pytest.fixture
def task_store() -> InMemoryTaskStore:
    """Create an in-memory task store."""
    return InMemoryTaskStore()


@pytest.fixture
def conversation_store() -> InMemoryConversationStore:
    """Create an in-memory conversation store."""
    return InMemoryConversationStore()


class MockProvider(IProvider):
    """Mock provider for testing."""

    def __init__(self, responses: list[str] | None = None):
        self._responses = responses or ["This is a mock response."]
        self._response_index = 0
        self._calls: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "mock"

    async def complete(
        self,
        messages: list[ProviderMessage],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ProviderResponse:
        self._calls.append({
            "method": "complete",
            "messages": messages,
            "model": model,
            "tools": tools,
        })

        response_text = self._responses[self._response_index % len(self._responses)]
        self._response_index += 1

        return ProviderResponse(content=response_text)

    async def stream(
        self,
        messages: list[ProviderMessage],
        model: str,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self._calls.append({
            "method": "stream",
            "messages": messages,
            "model": model,
            "tools": tools,
        })

        response_text = self._responses[self._response_index % len(self._responses)]
        self._response_index += 1

        # Stream word by word
        words = response_text.split()
        for i, word in enumerate(words):
            yield StreamChunk(
                content=word + (" " if i < len(words) - 1 else ""),
                is_final=(i == len(words) - 1),
            )

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        pass


@pytest.fixture
def mock_provider() -> MockProvider:
    """Create a mock provider for testing."""
    return MockProvider()


@pytest.fixture
def config_file_path(tmp_path: Path, sample_config: AgentConfig) -> Path:
    """Create a temporary config file."""
    import yaml

    config_path = tmp_path / "test-agent.yaml"

    # Convert config to dict for YAML
    config_dict = {
        "name": sample_config.name,
        "description": sample_config.description,
        "version": sample_config.version,
        "instructions": sample_config.instructions,
        "model": sample_config.model,
        "configuration": {
            "provider": "local",
        },
        "features": {
            "streaming": True,
            "tool_execution": True,
            "conversation_history": True,
        },
        "tools": [],
    }

    with open(config_path, "w") as f:
        yaml.dump(config_dict, f)

    return config_path
