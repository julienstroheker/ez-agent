"""Base storage interfaces and data types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _utc_now() -> datetime:
    """Get current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


class TaskStatus(str, Enum):
    """Task lifecycle states per A2A protocol."""

    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class MessagePart:
    """A part of a message (text, file, or data)."""

    type: str  # "text", "file", "data"
    content: str | bytes | dict[str, Any]
    mime_type: str | None = None
    name: str | None = None


@dataclass
class Message:
    """A message in a conversation."""

    id: str
    role: str  # "user" or "agent"
    parts: list[MessagePart]
    created_at: datetime = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Artifact:
    """An artifact produced by a task."""

    id: str
    name: str
    content: str | bytes
    mime_type: str
    created_at: datetime = field(default_factory=_utc_now)


@dataclass
class TaskData:
    """
    Data structure for a task.

    Follows the A2A protocol Task specification.
    """

    id: str
    session_id: str | None = None
    status: TaskStatus = TaskStatus.SUBMITTED
    messages: list[Message] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def add_message(self, message: Message) -> None:
        """Add a message to the task."""
        self.messages.append(message)
        self.updated_at = _utc_now()

    def add_artifact(self, artifact: Artifact) -> None:
        """Add an artifact to the task."""
        self.artifacts.append(artifact)
        self.updated_at = _utc_now()

    def set_status(self, status: TaskStatus, error: str | None = None) -> None:
        """Update the task status."""
        self.status = status
        self.error = error
        self.updated_at = _utc_now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "sessionId": self.session_id,
            "status": {"state": self.status.value},
            "messages": [
                {
                    "role": msg.role,
                    "parts": [
                        {"type": part.type, "content": part.content}
                        for part in msg.parts
                    ],
                }
                for msg in self.messages
            ],
            "artifacts": [
                {
                    "id": art.id,
                    "name": art.name,
                    "mimeType": art.mime_type,
                }
                for art in self.artifacts
            ],
            "metadata": self.metadata,
        }


@dataclass
class ConversationData:
    """
    Data structure for a conversation (session).

    A conversation can span multiple tasks.
    """

    id: str
    agent_name: str
    task_ids: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_task(self, task_id: str) -> None:
        """Add a task to the conversation."""
        if task_id not in self.task_ids:
            self.task_ids.append(task_id)
            self.updated_at = _utc_now()


class ITaskStore(ABC):
    """
    Abstract interface for task storage.

    Implementations can use in-memory, SQLite, Redis, or other backends.
    """

    @abstractmethod
    async def create(self, task: TaskData) -> TaskData:
        """
        Create a new task.

        Args:
            task: Task data to store.

        Returns:
            The created task with any server-side modifications.

        Raises:
            StorageError: If creation fails.
        """
        ...

    @abstractmethod
    async def get(self, task_id: str) -> TaskData | None:
        """
        Get a task by ID.

        Args:
            task_id: The task ID.

        Returns:
            The task data, or None if not found.
        """
        ...

    @abstractmethod
    async def update(self, task: TaskData) -> TaskData:
        """
        Update an existing task.

        Args:
            task: Task data with updated fields.

        Returns:
            The updated task.

        Raises:
            StorageError: If update fails or task not found.
        """
        ...

    @abstractmethod
    async def delete(self, task_id: str) -> bool:
        """
        Delete a task.

        Args:
            task_id: The task ID.

        Returns:
            True if deleted, False if not found.
        """
        ...

    @abstractmethod
    async def list(
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
            limit: Maximum number of results.
            offset: Number of results to skip.

        Returns:
            List of matching tasks.
        """
        ...

    @abstractmethod
    async def count(
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
        ...


class IConversationStore(ABC):
    """
    Abstract interface for conversation storage.

    Implementations can use in-memory, SQLite, Redis, or other backends.
    """

    @abstractmethod
    async def create(self, conversation: ConversationData) -> ConversationData:
        """
        Create a new conversation.

        Args:
            conversation: Conversation data to store.

        Returns:
            The created conversation.

        Raises:
            StorageError: If creation fails.
        """
        ...

    @abstractmethod
    async def get(self, conversation_id: str) -> ConversationData | None:
        """
        Get a conversation by ID.

        Args:
            conversation_id: The conversation ID.

        Returns:
            The conversation data, or None if not found.
        """
        ...

    @abstractmethod
    async def update(self, conversation: ConversationData) -> ConversationData:
        """
        Update an existing conversation.

        Args:
            conversation: Conversation data with updated fields.

        Returns:
            The updated conversation.

        Raises:
            StorageError: If update fails or conversation not found.
        """
        ...

    @abstractmethod
    async def delete(self, conversation_id: str) -> bool:
        """
        Delete a conversation.

        Args:
            conversation_id: The conversation ID.

        Returns:
            True if deleted, False if not found.
        """
        ...

    @abstractmethod
    async def list(
        self,
        agent_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConversationData]:
        """
        List conversations with optional filtering.

        Args:
            agent_name: Filter by agent name.
            limit: Maximum number of results.
            offset: Number of results to skip.

        Returns:
            List of matching conversations.
        """
        ...


class StorageError(Exception):
    """Base exception for storage errors."""

    def __init__(self, message: str, cause: Exception | None = None):
        super().__init__(message)
        self.message = message
        self.cause = cause
