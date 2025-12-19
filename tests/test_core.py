"""Tests for the core agent."""

from __future__ import annotations

import pytest

from ez_agent.core.agent import Agent, AgentContext
from ez_agent.core.task import TaskManager
from ez_agent.core.conversation import ConversationManager
from ez_agent.storage.base import TaskData, TaskStatus
from ez_agent.storage.memory import InMemoryConversationStore, InMemoryTaskStore

from tests.conftest import MockProvider


class TestTaskManager:
    """Test TaskManager."""

    @pytest.fixture
    def manager(self, task_store: InMemoryTaskStore) -> TaskManager:
        return TaskManager(task_store)

    async def test_create_task(self, manager: TaskManager):
        """Test creating a task."""
        task = await manager.create_task(
            session_id="session-1",
            initial_message="Hello",
        )

        assert task.id is not None
        assert task.session_id == "session-1"
        assert task.status == TaskStatus.SUBMITTED
        assert len(task.messages) == 1

    async def test_start_task(self, manager: TaskManager):
        """Test starting a task."""
        task = await manager.create_task()
        updated = await manager.start_task(task.id)

        assert updated.status == TaskStatus.WORKING

    async def test_complete_task(self, manager: TaskManager):
        """Test completing a task."""
        task = await manager.create_task()
        await manager.start_task(task.id)
        completed = await manager.complete_task(task.id, "Response text")

        assert completed.status == TaskStatus.COMPLETED
        assert len(completed.messages) == 1
        assert completed.messages[0].role == "agent"

    async def test_fail_task(self, manager: TaskManager):
        """Test failing a task."""
        task = await manager.create_task()
        await manager.start_task(task.id)
        failed = await manager.fail_task(task.id, "Something went wrong")

        assert failed.status == TaskStatus.FAILED
        assert failed.error == "Something went wrong"

    async def test_cancel_task(self, manager: TaskManager):
        """Test cancelling a task."""
        task = await manager.create_task()
        await manager.start_task(task.id)
        cancelled = await manager.cancel_task(task.id)

        assert cancelled.status == TaskStatus.CANCELLED

    async def test_cannot_cancel_completed_task(self, manager: TaskManager):
        """Test that completed tasks cannot be cancelled."""
        task = await manager.create_task()
        await manager.start_task(task.id)
        await manager.complete_task(task.id, "Done")

        with pytest.raises(ValueError, match="Cannot cancel"):
            await manager.cancel_task(task.id)

    async def test_add_messages(self, manager: TaskManager):
        """Test adding messages to a task."""
        task = await manager.create_task()

        await manager.add_user_message(task.id, "User message")
        await manager.add_agent_message(task.id, "Agent response")

        task = await manager.get_task(task.id)
        assert len(task.messages) == 2


class TestConversationManager:
    """Test ConversationManager."""

    @pytest.fixture
    def manager(
        self, conversation_store: InMemoryConversationStore
    ) -> ConversationManager:
        return ConversationManager(conversation_store, "TestAgent")

    async def test_create_conversation(self, manager: ConversationManager):
        """Test creating a conversation."""
        conv = await manager.create_conversation()

        assert conv.id is not None
        assert conv.agent_name == "TestAgent"

    async def test_get_or_create_existing(self, manager: ConversationManager):
        """Test getting existing conversation."""
        created = await manager.create_conversation(conversation_id="conv-1")
        retrieved = await manager.get_or_create_conversation(conversation_id="conv-1")

        assert retrieved.id == created.id

    async def test_get_or_create_new(self, manager: ConversationManager):
        """Test creating new conversation when not found."""
        conv = await manager.get_or_create_conversation(conversation_id="new-id")

        assert conv.id == "new-id"

    async def test_add_task(self, manager: ConversationManager):
        """Test adding a task to conversation."""
        conv = await manager.create_conversation()
        updated = await manager.add_task_to_conversation(conv.id, "task-1")

        assert "task-1" in updated.task_ids


class TestAgent:
    """Test Agent class."""

    @pytest.fixture
    def agent(
        self,
        sample_config,
        mock_provider: MockProvider,
        task_store: InMemoryTaskStore,
        conversation_store: InMemoryConversationStore,
    ) -> Agent:
        return Agent(
            config=sample_config,
            provider=mock_provider,
            task_store=task_store,
            conversation_store=conversation_store,
        )

    async def test_process_message(self, agent: Agent):
        """Test processing a message."""
        task, response = await agent.process_message("Hello, agent!")

        assert task is not None
        assert task.status == TaskStatus.COMPLETED
        assert response == "This is a mock response."

    async def test_process_message_with_session(self, agent: Agent):
        """Test message processing with session ID."""
        task1, _ = await agent.process_message("First message", session_id="session-1")
        task2, _ = await agent.process_message("Second message", session_id="session-1")

        assert task1.session_id == "session-1"
        assert task2.session_id == "session-1"

    async def test_stream_message(self, agent: Agent):
        """Test streaming a message."""
        chunks = []
        task = None

        async for t, chunk in agent.stream_message("Hello!"):
            task = t
            chunks.append(chunk)

        assert task is not None
        assert len(chunks) > 0
        # Last chunk should be final
        assert chunks[-1].is_final

    async def test_get_task(self, agent: Agent):
        """Test getting a task."""
        task, _ = await agent.process_message("Test")
        retrieved = await agent.get_task(task.id)

        assert retrieved is not None
        assert retrieved.id == task.id

    async def test_cancel_task(self, agent: Agent):
        """Test cancelling a task."""
        # Create a task
        task_manager = agent._task_manager
        task = await task_manager.create_task()
        await task_manager.start_task(task.id)

        cancelled = await agent.cancel_task(task.id)
        assert cancelled.status == TaskStatus.CANCELLED

    async def test_health_check(self, agent: Agent, mock_provider: MockProvider):
        """Test health check."""
        health = await agent.health_check()

        assert health["agent"] == "TestAgent"
        assert health["status"] == "healthy"
        assert health["provider"]["healthy"] is True


class TestAgentContext:
    """Test AgentContext."""

    def test_add_user_message(self):
        """Test adding a user message."""
        task = TaskData(id="test")
        context = AgentContext(task=task)

        context.add_user_message("Hello")

        assert len(context.messages) == 1
        assert context.messages[0].role.value == "user"
        assert context.messages[0].content == "Hello"

    def test_add_assistant_message(self):
        """Test adding an assistant message."""
        task = TaskData(id="test")
        context = AgentContext(task=task)

        context.add_assistant_message("Hi there")

        assert len(context.messages) == 1
        assert context.messages[0].role.value == "assistant"

    def test_add_tool_result(self):
        """Test adding a tool result."""
        task = TaskData(id="test")
        context = AgentContext(task=task)

        context.add_tool_result("call-123", "Result data")

        assert len(context.messages) == 1
        assert context.messages[0].role.value == "tool"
        assert context.messages[0].tool_call_id == "call-123"
