"""In-memory storage implementations."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from ez_agent.storage.base import (
    ConversationData,
    IConversationStore,
    ITaskStore,
    StorageError,
    TaskData,
    TaskStatus,
)


def _utc_now() -> datetime:
    """Get current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


class InMemoryTaskStore(ITaskStore):
    """
    In-memory implementation of task storage.

    Suitable for development and testing. Data is lost on restart.
    Thread-safe using asyncio locks.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, TaskData] = {}
        self._lock = asyncio.Lock()

    async def create(self, task: TaskData) -> TaskData:
        """Create a new task."""
        async with self._lock:
            if task.id in self._tasks:
                raise StorageError(f"Task with ID '{task.id}' already exists")

            # Ensure timestamps are set
            now = _utc_now()
            task.created_at = now
            task.updated_at = now

            self._tasks[task.id] = task
            return task

    async def get(self, task_id: str) -> TaskData | None:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    async def update(self, task: TaskData) -> TaskData:
        """Update an existing task."""
        async with self._lock:
            if task.id not in self._tasks:
                raise StorageError(f"Task with ID '{task.id}' not found")

            task.updated_at = _utc_now()
            self._tasks[task.id] = task
            return task

    async def delete(self, task_id: str) -> bool:
        """Delete a task."""
        async with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                return True
            return False

    async def list(
        self,
        session_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TaskData]:
        """List tasks with optional filtering."""
        tasks = list(self._tasks.values())

        # Apply filters
        if session_id is not None:
            tasks = [t for t in tasks if t.session_id == session_id]
        if status is not None:
            tasks = [t for t in tasks if t.status == status]

        # Sort by created_at descending
        tasks.sort(key=lambda t: t.created_at, reverse=True)

        # Apply pagination
        return tasks[offset : offset + limit]

    async def count(
        self,
        session_id: str | None = None,
        status: TaskStatus | None = None,
    ) -> int:
        """Count tasks with optional filtering."""
        tasks = list(self._tasks.values())

        if session_id is not None:
            tasks = [t for t in tasks if t.session_id == session_id]
        if status is not None:
            tasks = [t for t in tasks if t.status == status]

        return len(tasks)

    async def clear(self) -> None:
        """Clear all tasks (useful for testing)."""
        async with self._lock:
            self._tasks.clear()


class InMemoryConversationStore(IConversationStore):
    """
    In-memory implementation of conversation storage.

    Suitable for development and testing. Data is lost on restart.
    Thread-safe using asyncio locks.
    """

    def __init__(self) -> None:
        self._conversations: dict[str, ConversationData] = {}
        self._lock = asyncio.Lock()

    async def create(self, conversation: ConversationData) -> ConversationData:
        """Create a new conversation."""
        async with self._lock:
            if conversation.id in self._conversations:
                raise StorageError(
                    f"Conversation with ID '{conversation.id}' already exists"
                )

            now = _utc_now()
            conversation.created_at = now
            conversation.updated_at = now

            self._conversations[conversation.id] = conversation
            return conversation

    async def get(self, conversation_id: str) -> ConversationData | None:
        """Get a conversation by ID."""
        return self._conversations.get(conversation_id)

    async def update(self, conversation: ConversationData) -> ConversationData:
        """Update an existing conversation."""
        async with self._lock:
            if conversation.id not in self._conversations:
                raise StorageError(
                    f"Conversation with ID '{conversation.id}' not found"
                )

            conversation.updated_at = _utc_now()
            self._conversations[conversation.id] = conversation
            return conversation

    async def delete(self, conversation_id: str) -> bool:
        """Delete a conversation."""
        async with self._lock:
            if conversation_id in self._conversations:
                del self._conversations[conversation_id]
                return True
            return False

    async def list(
        self,
        agent_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConversationData]:
        """List conversations with optional filtering."""
        conversations = list(self._conversations.values())

        if agent_name is not None:
            conversations = [c for c in conversations if c.agent_name == agent_name]

        # Sort by created_at descending
        conversations.sort(key=lambda c: c.created_at, reverse=True)

        return conversations[offset : offset + limit]

    async def clear(self) -> None:
        """Clear all conversations (useful for testing)."""
        async with self._lock:
            self._conversations.clear()
