"""Tests for storage implementations."""

from __future__ import annotations

import pytest

from ez_agent.storage.base import (
    ConversationData,
    StorageError,
    TaskData,
    TaskStatus,
)
from ez_agent.storage.memory import InMemoryConversationStore, InMemoryTaskStore


class TestInMemoryTaskStore:
    """Test in-memory task storage."""

    @pytest.fixture
    def store(self) -> InMemoryTaskStore:
        return InMemoryTaskStore()

    @pytest.fixture
    def sample_task(self) -> TaskData:
        return TaskData(
            id="task-123",
            session_id="session-456",
            status=TaskStatus.SUBMITTED,
        )

    async def test_create_task(self, store: InMemoryTaskStore, sample_task: TaskData):
        """Test creating a task."""
        created = await store.create(sample_task)

        assert created.id == sample_task.id
        assert created.session_id == sample_task.session_id
        assert created.status == TaskStatus.SUBMITTED
        assert created.created_at is not None

    async def test_create_duplicate_raises(
        self, store: InMemoryTaskStore, sample_task: TaskData
    ):
        """Test that creating duplicate task raises error."""
        await store.create(sample_task)

        with pytest.raises(StorageError, match="already exists"):
            await store.create(sample_task)

    async def test_get_task(self, store: InMemoryTaskStore, sample_task: TaskData):
        """Test retrieving a task."""
        await store.create(sample_task)

        retrieved = await store.get(sample_task.id)
        assert retrieved is not None
        assert retrieved.id == sample_task.id

    async def test_get_nonexistent_returns_none(self, store: InMemoryTaskStore):
        """Test that getting nonexistent task returns None."""
        result = await store.get("nonexistent")
        assert result is None

    async def test_update_task(self, store: InMemoryTaskStore, sample_task: TaskData):
        """Test updating a task."""
        await store.create(sample_task)

        sample_task.set_status(TaskStatus.WORKING)
        updated = await store.update(sample_task)

        assert updated.status == TaskStatus.WORKING
        assert updated.updated_at > updated.created_at

    async def test_update_nonexistent_raises(
        self, store: InMemoryTaskStore, sample_task: TaskData
    ):
        """Test that updating nonexistent task raises error."""
        with pytest.raises(StorageError, match="not found"):
            await store.update(sample_task)

    async def test_delete_task(self, store: InMemoryTaskStore, sample_task: TaskData):
        """Test deleting a task."""
        await store.create(sample_task)

        result = await store.delete(sample_task.id)
        assert result is True

        retrieved = await store.get(sample_task.id)
        assert retrieved is None

    async def test_delete_nonexistent_returns_false(self, store: InMemoryTaskStore):
        """Test that deleting nonexistent task returns False."""
        result = await store.delete("nonexistent")
        assert result is False

    async def test_list_tasks(self, store: InMemoryTaskStore):
        """Test listing tasks."""
        # Create multiple tasks
        for i in range(5):
            await store.create(TaskData(id=f"task-{i}", session_id="session-1"))

        tasks = await store.list()
        assert len(tasks) == 5

    async def test_list_tasks_by_session(self, store: InMemoryTaskStore):
        """Test filtering tasks by session."""
        await store.create(TaskData(id="task-1", session_id="session-1"))
        await store.create(TaskData(id="task-2", session_id="session-1"))
        await store.create(TaskData(id="task-3", session_id="session-2"))

        tasks = await store.list(session_id="session-1")
        assert len(tasks) == 2

    async def test_list_tasks_by_status(self, store: InMemoryTaskStore):
        """Test filtering tasks by status."""
        task1 = TaskData(id="task-1")
        task1.set_status(TaskStatus.COMPLETED)
        await store.create(task1)

        task2 = TaskData(id="task-2")
        task2.set_status(TaskStatus.FAILED)
        await store.create(task2)

        completed = await store.list(status=TaskStatus.COMPLETED)
        assert len(completed) == 1
        assert completed[0].id == "task-1"

    async def test_list_with_pagination(self, store: InMemoryTaskStore):
        """Test pagination in list."""
        for i in range(10):
            await store.create(TaskData(id=f"task-{i}"))

        page1 = await store.list(limit=3, offset=0)
        page2 = await store.list(limit=3, offset=3)

        assert len(page1) == 3
        assert len(page2) == 3
        assert page1[0].id != page2[0].id

    async def test_count_tasks(self, store: InMemoryTaskStore):
        """Test counting tasks."""
        for i in range(5):
            await store.create(TaskData(id=f"task-{i}"))

        count = await store.count()
        assert count == 5


class TestInMemoryConversationStore:
    """Test in-memory conversation storage."""

    @pytest.fixture
    def store(self) -> InMemoryConversationStore:
        return InMemoryConversationStore()

    @pytest.fixture
    def sample_conversation(self) -> ConversationData:
        return ConversationData(
            id="conv-123",
            agent_name="TestAgent",
        )

    async def test_create_conversation(
        self, store: InMemoryConversationStore, sample_conversation: ConversationData
    ):
        """Test creating a conversation."""
        created = await store.create(sample_conversation)

        assert created.id == sample_conversation.id
        assert created.agent_name == "TestAgent"

    async def test_add_task_to_conversation(
        self, store: InMemoryConversationStore, sample_conversation: ConversationData
    ):
        """Test adding a task to a conversation."""
        await store.create(sample_conversation)

        sample_conversation.add_task("task-1")
        updated = await store.update(sample_conversation)

        assert "task-1" in updated.task_ids

    async def test_list_by_agent(self, store: InMemoryConversationStore):
        """Test filtering conversations by agent name."""
        await store.create(ConversationData(id="conv-1", agent_name="Agent1"))
        await store.create(ConversationData(id="conv-2", agent_name="Agent1"))
        await store.create(ConversationData(id="conv-3", agent_name="Agent2"))

        convs = await store.list(agent_name="Agent1")
        assert len(convs) == 2
