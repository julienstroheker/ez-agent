"""A2A protocol data models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    """Get current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


class TaskState(str, Enum):
    """Task states per A2A protocol."""

    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class MessageRole(str, Enum):
    """Message roles."""

    USER = "user"
    AGENT = "agent"


class TextPart(BaseModel):
    """Text content part."""

    type: Literal["text"] = "text"
    text: str


class FilePart(BaseModel):
    """File content part."""

    type: Literal["file"] = "file"
    file: dict[str, Any]  # Contains uri, name, mimeType


class DataPart(BaseModel):
    """Structured data part."""

    type: Literal["data"] = "data"
    data: dict[str, Any]


# Union type for message parts
MessagePart = TextPart | FilePart | DataPart


class Message(BaseModel):
    """A message in the A2A protocol."""

    role: MessageRole
    parts: list[MessagePart]
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskStatus(BaseModel):
    """Task status information."""

    state: TaskState
    message: str | None = None
    timestamp: datetime = Field(default_factory=_utc_now)


class Artifact(BaseModel):
    """An artifact produced by a task."""

    id: str
    name: str
    mimeType: str
    parts: list[MessagePart] = Field(default_factory=list)


class Task(BaseModel):
    """A task in the A2A protocol."""

    id: str
    sessionId: str | None = None
    status: TaskStatus
    messages: list[Message] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SendMessageRequest(BaseModel):
    """Request to send a message to an agent."""

    message: Message
    sessionId: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SendMessageResponse(BaseModel):
    """Response from sending a message."""

    task: Task


class GetTaskRequest(BaseModel):
    """Request to get a task."""

    id: str
    historyLength: int | None = None


class CancelTaskRequest(BaseModel):
    """Request to cancel a task."""

    id: str


class ListTasksRequest(BaseModel):
    """Request to list tasks."""

    sessionId: str | None = None
    limit: int = 100
    offset: int = 0


class ListTasksResponse(BaseModel):
    """Response from listing tasks."""

    tasks: list[Task]
    total: int


class AgentSkill(BaseModel):
    """A skill/capability of an agent."""

    id: str
    name: str
    description: str
    inputModes: list[str] = Field(default_factory=lambda: ["text"])
    outputModes: list[str] = Field(default_factory=lambda: ["text"])


class AgentCapabilities(BaseModel):
    """Capabilities of an agent."""

    streaming: bool = True
    pushNotifications: bool = False
    stateTransitionHistory: bool = True


class AgentCard(BaseModel):
    """
    Agent Card for discovery per A2A specification.

    Exposed at /.well-known/agent-card.json
    """

    name: str
    description: str
    version: str
    url: str
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    skills: list[AgentSkill] = Field(default_factory=list)
    defaultInputModes: list[str] = Field(default_factory=lambda: ["text"])
    defaultOutputModes: list[str] = Field(default_factory=lambda: ["text"])
    metadata: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Error response."""

    error: str
    code: str
    details: dict[str, Any] = Field(default_factory=dict)


class StreamEvent(BaseModel):
    """Server-Sent Event for streaming."""

    event: str  # "message", "status", "artifact", "done", "error"
    data: dict[str, Any]
