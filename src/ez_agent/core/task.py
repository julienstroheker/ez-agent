"""Task management for the agent runtime."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from ez_agent.storage.base import (
    Artifact,
    ITaskStore,
    Message,
    MessagePart,
    TaskData,
    TaskStatus,
)

if TYPE_CHECKING:
    pass


class TaskManager:
    """
    Manages task lifecycle for an agent.

    Provides high-level operations for creating, updating, and querying tasks.
    Uses the storage abstraction for persistence.
    """

    def __init__(self, store: ITaskStore) -> None:
        """
        Initialize the task manager.

        Args:
            store: Task storage implementation.
        """
        self._store = store

    async def create_task(
        self,
        session_id: str | None = None,
        initial_message: str | None = None,
        metadata: dict | None = None,
    ) -> TaskData:
        """
        Create a new task.

        Args:
            session_id: Optional session/conversation ID.
            initial_message: Optional initial user message.
            metadata: Optional task metadata.

        Returns:
            The created task.
        """
        task_id = str(uuid.uuid4())
        task = TaskData(
            id=task_id,
            session_id=session_id,
            status=TaskStatus.SUBMITTED,
            metadata=metadata or {},
        )

        if initial_message:
            message = Message(
                id=str(uuid.uuid4()),
                role="user",
                parts=[MessagePart(type="text", content=initial_message)],
            )
            task.add_message(message)

        return await self._store.create(task)

    async def get_task(self, task_id: str) -> TaskData | None:
        """
        Get a task by ID.

        Args:
            task_id: The task ID.

        Returns:
            The task, or None if not found.
        """
        return await self._store.get(task_id)

    async def start_task(self, task_id: str) -> TaskData:
        """
        Mark a task as working.

        Args:
            task_id: The task ID.

        Returns:
            The updated task.

        Raises:
            ValueError: If task not found.
        """
        task = await self._store.get(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found")

        task.set_status(TaskStatus.WORKING)
        return await self._store.update(task)

    async def complete_task(
        self,
        task_id: str,
        response: str,
        artifacts: list[Artifact] | None = None,
    ) -> TaskData:
        """
        Mark a task as completed with a response.

        Args:
            task_id: The task ID.
            response: The agent's response.
            artifacts: Optional list of artifacts produced.

        Returns:
            The updated task.

        Raises:
            ValueError: If task not found.
        """
        task = await self._store.get(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found")

        # Add the agent's response
        message = Message(
            id=str(uuid.uuid4()),
            role="agent",
            parts=[MessagePart(type="text", content=response)],
        )
        task.add_message(message)

        # Add any artifacts
        if artifacts:
            for artifact in artifacts:
                task.add_artifact(artifact)

        task.set_status(TaskStatus.COMPLETED)
        return await self._store.update(task)

    async def fail_task(self, task_id: str, error: str) -> TaskData:
        """
        Mark a task as failed.

        Args:
            task_id: The task ID.
            error: Error message.

        Returns:
            The updated task.

        Raises:
            ValueError: If task not found.
        """
        task = await self._store.get(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found")

        task.set_status(TaskStatus.FAILED, error=error)
        return await self._store.update(task)

    async def cancel_task(self, task_id: str) -> TaskData:
        """
        Cancel a task.

        Args:
            task_id: The task ID.

        Returns:
            The updated task.

        Raises:
            ValueError: If task not found or not cancellable.
        """
        task = await self._store.get(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found")

        # Can only cancel tasks that are not already terminal
        terminal_states = {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.REJECTED,
        }
        if task.status in terminal_states:
            raise ValueError(f"Cannot cancel task in status '{task.status.value}'")

        task.set_status(TaskStatus.CANCELLED)
        return await self._store.update(task)

    async def add_user_message(self, task_id: str, content: str) -> TaskData:
        """
        Add a user message to a task.

        Args:
            task_id: The task ID.
            content: Message content.

        Returns:
            The updated task.

        Raises:
            ValueError: If task not found.
        """
        task = await self._store.get(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found")

        message = Message(
            id=str(uuid.uuid4()),
            role="user",
            parts=[MessagePart(type="text", content=content)],
        )
        task.add_message(message)
        return await self._store.update(task)

    async def add_agent_message(self, task_id: str, content: str) -> TaskData:
        """
        Add an agent message to a task.

        Args:
            task_id: The task ID.
            content: Message content.

        Returns:
            The updated task.

        Raises:
            ValueError: If task not found.
        """
        task = await self._store.get(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found")

        message = Message(
            id=str(uuid.uuid4()),
            role="agent",
            parts=[MessagePart(type="text", content=content)],
        )
        task.add_message(message)
        return await self._store.update(task)

    async def request_input(self, task_id: str, prompt: str) -> TaskData:
        """
        Mark a task as requiring user input.

        Args:
            task_id: The task ID.
            prompt: Prompt for the user.

        Returns:
            The updated task.

        Raises:
            ValueError: If task not found.
        """
        task = await self._store.get(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found")

        # Add the prompt as an agent message
        message = Message(
            id=str(uuid.uuid4()),
            role="agent",
            parts=[MessagePart(type="text", content=prompt)],
        )
        task.add_message(message)

        task.set_status(TaskStatus.INPUT_REQUIRED)
        return await self._store.update(task)

    async def list_tasks(
        self,
        session_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TaskData]:
        """
        List tasks with optional filtering.

        Args:
            session_id: Filter by session ID.
            status: Filter by status.
            limit: Maximum results.
            offset: Results to skip.

        Returns:
            List of matching tasks.
        """
        return await self._store.list(
            session_id=session_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def count_tasks(
        self,
        session_id: str | None = None,
        status: TaskStatus | None = None,
    ) -> int:
        """
        Count tasks with optional filtering.

        Args:
            session_id: Filter by session ID.
            status: Filter by status.

        Returns:
            Number of matching tasks.
        """
        return await self._store.count(session_id=session_id, status=status)
