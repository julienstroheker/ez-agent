"""Factory for creating agent instances from configuration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ez_agent.config.models import AgentConfig
from ez_agent.core.agent import Agent
from ez_agent.middleware.base import MiddlewareChain
from ez_agent.middleware.logging import LoggingMiddleware
from ez_agent.middleware.metrics import MetricsMiddleware
from ez_agent.providers.registry import get_provider
from ez_agent.storage.memory import InMemoryConversationStore, InMemoryTaskStore
from ez_agent.tools.registry import ToolRegistry

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def create_agent_from_config(
    config: AgentConfig,
    task_store: InMemoryTaskStore | None = None,
    conversation_store: InMemoryConversationStore | None = None,
) -> Agent:
    """
    Create an agent instance from configuration.

    Args:
        config: Agent configuration.
        task_store: Optional task store (creates in-memory if not provided).
        conversation_store: Optional conversation store (creates in-memory if not provided).

    Returns:
        Configured Agent instance.
    """
    # Create storage
    if task_store is None:
        task_store = InMemoryTaskStore()
    if conversation_store is None:
        conversation_store = InMemoryConversationStore()

    # Create provider
    provider = get_provider(config.configuration)
    
    # Set the agent name and instructions on the provider
    provider.set_agent_name(config.name)
    provider.set_instructions(config.instructions)

    # Create tool registry
    tool_registry = None
    if config.features.tool_execution and config.tools:
        tool_registry = ToolRegistry()
        for tool_config in config.tools:
            try:
                tool_registry.register_from_config(tool_config)
                logger.info(f"Registered tool: {tool_config.name}")
            except Exception as e:
                logger.error(f"Failed to register tool {tool_config.name}: {e}")

    # Create middleware chain
    middleware = _create_middleware_chain(config)

    # Create agent
    agent = Agent(
        config=config,
        provider=provider,
        task_store=task_store,
        conversation_store=conversation_store,
        tool_registry=tool_registry,
        middleware=middleware,
    )

    return agent


def _create_middleware_chain(config: AgentConfig) -> MiddlewareChain:
    """Create the middleware chain based on configuration."""
    chain = MiddlewareChain()

    # Always add metrics
    chain.add(MetricsMiddleware())

    # Add logging based on config
    log_level = getattr(logging, config.configuration.logging.level.value, logging.INFO)
    chain.add(LoggingMiddleware(log_level=log_level))

    # Auth middleware is handled at the HTTP layer, not here

    return chain
