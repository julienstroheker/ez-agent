"""Main agent implementation."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncIterator

from ez_agent.config.models import AgentConfig
from ez_agent.core.conversation import ConversationManager
from ez_agent.core.task import TaskManager
from ez_agent.providers.base import (
    IProvider,
    ProviderMessage,
    ProviderResponse,
    StreamChunk,
    ToolCall,
)
from ez_agent.storage.base import (
    ConversationData,
    IConversationStore,
    ITaskStore,
    TaskData,
    TaskStatus,
)

if TYPE_CHECKING:
    from ez_agent.middleware.base import MiddlewareChain
    from ez_agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    """
    Context passed through the agent processing pipeline.

    Contains all information needed to process a request.
    """

    task: TaskData
    conversation: ConversationData | None = None
    messages: list[ProviderMessage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def add_user_message(self, content: str) -> None:
        """Add a user message to the context."""
        self.messages.append(ProviderMessage.user(content))

    def add_assistant_message(self, content: str, tool_calls: list[ToolCall] | None = None) -> None:
        """Add an assistant message to the context."""
        self.messages.append(ProviderMessage.assistant(content, tool_calls))

    def add_tool_result(self, tool_call_id: str, content: str, is_error: bool = False) -> None:
        """Add a tool result to the context."""
        self.messages.append(ProviderMessage.tool_result(tool_call_id, content, is_error))


class Agent:
    """
    Main agent class that orchestrates message processing.

    The agent:
    1. Receives user messages
    2. Passes them through middleware
    3. Sends to the LLM provider
    4. Handles tool calls if needed
    5. Returns the response
    """

    def __init__(
        self,
        config: AgentConfig,
        provider: IProvider,
        task_store: ITaskStore,
        conversation_store: IConversationStore,
        tool_registry: "ToolRegistry | None" = None,
        middleware: "MiddlewareChain | None" = None,
    ) -> None:
        """
        Initialize the agent.

        Args:
            config: Agent configuration.
            provider: LLM provider instance.
            task_store: Task storage implementation.
            conversation_store: Conversation storage implementation.
            tool_registry: Optional tool registry for function calling.
            middleware: Optional middleware chain.
        """
        self._config = config
        self._provider = provider
        self._tool_registry = tool_registry
        self._middleware = middleware

        self._task_manager = TaskManager(task_store)
        self._conversation_manager = ConversationManager(
            conversation_store,
            config.name,
        )

    @property
    def config(self) -> AgentConfig:
        """Get the agent configuration."""
        return self._config

    @property
    def name(self) -> str:
        """Get the agent name."""
        return self._config.name

    async def process_message(
        self,
        message: str,
        session_id: str | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[TaskData, str]:
        """
        Process a user message and return the response.

        Args:
            message: User message content.
            session_id: Optional session/conversation ID.
            task_id: Optional existing task ID to continue.
            metadata: Optional request metadata.

        Returns:
            Tuple of (task, response_text).
        """
        # Get or create conversation
        conversation = None
        if session_id or self._config.features.conversation_history:
            conversation = await self._conversation_manager.get_or_create_conversation(
                conversation_id=session_id,
            )

        # Get or create task
        if task_id:
            task = await self._task_manager.get_task(task_id)
            if not task:
                raise ValueError(f"Task '{task_id}' not found")
            await self._task_manager.add_user_message(task_id, message)
            task = await self._task_manager.get_task(task_id)
        else:
            task = await self._task_manager.create_task(
                session_id=conversation.id if conversation else None,
                initial_message=message,
                metadata=metadata,
            )
            if conversation:
                await self._conversation_manager.add_task_to_conversation(
                    conversation.id,
                    task.id,
                )

        # Build context
        context = AgentContext(
            task=task,
            conversation=conversation,
            metadata=metadata or {},
        )

        # Build message history
        context.messages.append(ProviderMessage.system(self._config.instructions))
        await self._build_message_history(context)
        context.add_user_message(message)

        # Mark task as working
        await self._task_manager.start_task(task.id)

        try:
            # Get tool definitions if available
            tools = None
            if self._tool_registry and self._config.features.tool_execution:
                tools = self._tool_registry.get_tool_definitions()

            # Run through middleware if present
            if self._middleware:
                response = await self._middleware.process(
                    context,
                    lambda ctx: self._execute_completion(ctx, tools),
                )
            else:
                response = await self._execute_completion(context, tools)

            # Handle tool calls if needed
            response = await self._handle_tool_calls(context, response, tools)

            # Complete the task
            task = await self._task_manager.complete_task(task.id, response.content)

            return task, response.content

        except Exception as e:
            logger.exception(f"Error processing message: {e}")
            await self._task_manager.fail_task(task.id, str(e))
            raise

    async def stream_message(
        self,
        message: str,
        session_id: str | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[tuple[TaskData, StreamChunk]]:
        """
        Process a user message with streaming response.

        Args:
            message: User message content.
            session_id: Optional session/conversation ID.
            task_id: Optional existing task ID to continue.
            metadata: Optional request metadata.

        Yields:
            Tuples of (task, stream_chunk).
        """
        if not self._config.features.streaming:
            # Fall back to non-streaming
            task, response = await self.process_message(
                message, session_id, task_id, metadata
            )
            yield task, StreamChunk(content=response, is_final=True)
            return

        # Get or create conversation
        conversation = None
        if session_id or self._config.features.conversation_history:
            conversation = await self._conversation_manager.get_or_create_conversation(
                conversation_id=session_id,
            )

        # Get or create task
        if task_id:
            task = await self._task_manager.get_task(task_id)
            if not task:
                raise ValueError(f"Task '{task_id}' not found")
            await self._task_manager.add_user_message(task_id, message)
            task = await self._task_manager.get_task(task_id)
        else:
            task = await self._task_manager.create_task(
                session_id=conversation.id if conversation else None,
                initial_message=message,
                metadata=metadata,
            )
            if conversation:
                await self._conversation_manager.add_task_to_conversation(
                    conversation.id,
                    task.id,
                )

        # Build context
        context = AgentContext(
            task=task,
            conversation=conversation,
            metadata=metadata or {},
        )

        context.messages.append(ProviderMessage.system(self._config.instructions))
        await self._build_message_history(context)
        context.add_user_message(message)

        await self._task_manager.start_task(task.id)

        try:
            tools = None
            if self._tool_registry and self._config.features.tool_execution:
                tools = self._tool_registry.get_tool_definitions()

            full_content = ""
            accumulated_tool_calls: list[ToolCall] = []

            async for chunk in self._provider.stream(
                messages=context.messages,
                model=self._config.model,
                tools=tools,
            ):
                full_content += chunk.content
                accumulated_tool_calls.extend(chunk.tool_calls)
                yield task, chunk

            # Handle tool calls if any
            if accumulated_tool_calls:
                context.add_assistant_message("", accumulated_tool_calls)
                response = await self._handle_tool_calls(
                    context,
                    ProviderResponse(content=full_content, tool_calls=accumulated_tool_calls),
                    tools,
                )
                yield task, StreamChunk(content=response.content, is_final=True)
                full_content = response.content

            task = await self._task_manager.complete_task(task.id, full_content)
            yield task, StreamChunk(is_final=True, finish_reason="stop")

        except Exception as e:
            logger.exception(f"Error streaming message: {e}")
            await self._task_manager.fail_task(task.id, str(e))
            raise

    async def _build_message_history(self, context: AgentContext) -> None:
        """Build message history from previous tasks in the conversation."""
        if not context.conversation or not self._config.features.conversation_history:
            return

        # Get previous tasks in this conversation
        for task_id in context.conversation.task_ids:
            if task_id == context.task.id:
                continue  # Skip current task

            task = await self._task_manager.get_task(task_id)
            if not task:
                continue

            for msg in task.messages:
                # Only include text parts
                for part in msg.parts:
                    if part.type == "text" and isinstance(part.content, str):
                        if msg.role == "user":
                            context.messages.append(ProviderMessage.user(part.content))
                        elif msg.role == "agent":
                            context.messages.append(ProviderMessage.assistant(part.content))

    async def _execute_completion(
        self,
        context: AgentContext,
        tools: list[dict[str, Any]] | None,
    ) -> ProviderResponse:
        """Execute the LLM completion."""
        return await self._provider.complete(
            messages=context.messages,
            model=self._config.model,
            tools=tools,
        )

    async def _handle_tool_calls(
        self,
        context: AgentContext,
        response: ProviderResponse,
        tools: list[dict[str, Any]] | None,
        max_iterations: int = 10,
    ) -> ProviderResponse:
        """
        Handle tool calls in a loop until completion.

        Args:
            context: Agent context.
            response: Initial provider response.
            tools: Tool definitions.
            max_iterations: Maximum tool call iterations to prevent infinite loops.

        Returns:
            Final response after all tool calls.
        """
        iteration = 0

        while response.requires_action and iteration < max_iterations:
            iteration += 1
            logger.debug(f"Handling tool calls, iteration {iteration}")

            if not self._tool_registry:
                raise ValueError("Tool calls received but no tool registry configured")

            # Add assistant message with tool calls
            context.add_assistant_message(response.content, response.tool_calls)

            # Execute each tool call
            for tool_call in response.tool_calls:
                logger.info(f"Executing tool: {tool_call.name}")
                try:
                    result = await self._tool_registry.execute(
                        tool_call.name,
                        tool_call.arguments,
                    )
                    context.add_tool_result(tool_call.id, result)
                except Exception as e:
                    logger.error(f"Tool execution failed: {e}")
                    context.add_tool_result(
                        tool_call.id,
                        f"Error: {e}",
                        is_error=True,
                    )

            # Get next response
            response = await self._provider.complete(
                messages=context.messages,
                model=self._config.model,
                tools=tools,
            )

        if iteration >= max_iterations:
            logger.warning(f"Max tool call iterations ({max_iterations}) reached")

        return response

    async def get_task(self, task_id: str) -> TaskData | None:
        """Get a task by ID."""
        return await self._task_manager.get_task(task_id)

    async def cancel_task(self, task_id: str) -> TaskData:
        """Cancel a task."""
        return await self._task_manager.cancel_task(task_id)

    async def list_tasks(
        self,
        session_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 100,
    ) -> list[TaskData]:
        """List tasks."""
        return await self._task_manager.list_tasks(
            session_id=session_id,
            status=status,
            limit=limit,
        )

    async def health_check(self) -> dict[str, Any]:
        """Check agent health."""
        provider_healthy = await self._provider.health_check()
        return {
            "agent": self.name,
            "status": "healthy" if provider_healthy else "degraded",
            "provider": {
                "name": self._provider.name,
                "healthy": provider_healthy,
            },
        }

    async def close(self) -> None:
        """Clean up resources."""
        await self._provider.close()
