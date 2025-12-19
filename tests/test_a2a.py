"""Tests for A2A protocol server."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from typing import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ez_agent.a2a.models import (
    AgentCard,
    Message,
    MessageRole,
    SendMessageRequest,
    Task,
    TaskState,
    TextPart,
)
from ez_agent.config.models import (
    AgentConfig,
    ConfigurationSettings,
    FeatureFlags,
    ProviderType,
)


@pytest.fixture
def test_config() -> AgentConfig:
    """Create test configuration."""
    return AgentConfig(
        name="TestA2AAgent",
        description="A test A2A agent",
        version="1.0.0",
        instructions="Be helpful.",
        model="gpt-4o",
        configuration=ConfigurationSettings(provider=ProviderType.LOCAL),
        features=FeatureFlags(streaming=False),
    )


@pytest.fixture
def mock_agent():
    """Create a mock agent."""
    agent = MagicMock()
    agent.config = MagicMock()
    agent.config.name = "TestA2AAgent"
    agent.health_check = AsyncMock(return_value={
        "agent": "TestA2AAgent",
        "status": "healthy",
        "provider": {"healthy": True},
    })
    agent.close = AsyncMock()
    
    # Mock tool registry (empty)
    agent._tool_registry = None
    
    # Track created tasks
    created_tasks: dict[str, "TaskData"] = {}
    
    # Mock process_message to return a task and response
    from ez_agent.storage.base import TaskData, TaskStatus
    
    def create_task(session_id=None):
        import uuid
        task = TaskData(id=str(uuid.uuid4()), session_id=session_id or "session-456")
        task.set_status(TaskStatus.COMPLETED)
        created_tasks[task.id] = task
        return task
    
    async def mock_process_message(message, session_id=None, metadata=None):
        task = create_task(session_id)
        return (task, "Test response")
    
    agent.process_message = AsyncMock(side_effect=mock_process_message)
    
    # For get_task - return None for nonexistent
    async def mock_get_task(task_id):
        return created_tasks.get(task_id)
    
    agent.get_task = AsyncMock(side_effect=mock_get_task)
    
    # Mock task listing - return all created tasks
    async def mock_list_tasks(session_id=None, limit=100):
        tasks = list(created_tasks.values())
        if session_id:
            tasks = [t for t in tasks if t.session_id == session_id]
        return tasks[:limit]
    
    agent.list_tasks = AsyncMock(side_effect=mock_list_tasks)
    
    return agent


@pytest.fixture
def client(test_config: AgentConfig, mock_agent) -> Generator[TestClient, None, None]:
    """Create test client with mocked agent."""
    from ez_agent.a2a.server import create_app
    
    # Patch create_agent_from_config to return our mock
    with patch("ez_agent.a2a.server.create_agent_from_config", return_value=mock_agent):
        app = create_app(test_config)
        with TestClient(app) as client:
            yield client


class TestAgentCard:
    """Test agent card endpoint."""

    def test_get_agent_card(self, client: TestClient):
        """Test retrieving agent card."""
        response = client.get("/.well-known/agent-card.json")

        assert response.status_code == 200
        data = response.json()

        assert data["name"] == "TestA2AAgent"
        assert data["description"] == "A test A2A agent"
        assert data["version"] == "1.0.0"
        assert "capabilities" in data


class TestSendMessage:
    """Test message sending endpoint."""

    def test_send_message(self, client: TestClient):
        """Test sending a message."""
        request = SendMessageRequest(
            message=Message(
                role=MessageRole.USER,
                parts=[TextPart(text="Hello, agent!")],
            ),
        )

        response = client.post(
            "/v1/message:send",
            json=request.model_dump(),
        )

        assert response.status_code == 200
        data = response.json()

        assert "task" in data
        assert data["task"]["status"]["state"] in [
            TaskState.COMPLETED.value,
            TaskState.WORKING.value,
        ]

    def test_send_message_with_session(self, client: TestClient):
        """Test sending message with session ID."""
        request = SendMessageRequest(
            message=Message(
                role=MessageRole.USER,
                parts=[TextPart(text="Hello!")],
            ),
            sessionId="test-session",
        )

        response = client.post(
            "/v1/message:send",
            json=request.model_dump(),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["task"]["sessionId"] == "test-session"

    def test_send_empty_message_fails(self, client: TestClient):
        """Test that empty message fails."""
        request = {
            "message": {
                "role": "user",
                "parts": [],
            }
        }

        response = client.post("/v1/message:send", json=request)
        assert response.status_code == 400


class TestTaskEndpoints:
    """Test task management endpoints."""

    def test_get_task(self, client: TestClient):
        """Test getting a task."""
        # First create a task
        request = SendMessageRequest(
            message=Message(
                role=MessageRole.USER,
                parts=[TextPart(text="Test")],
            ),
        )
        create_response = client.post(
            "/v1/message:send",
            json=request.model_dump(),
        )
        task_id = create_response.json()["task"]["id"]

        # Get the task
        response = client.get(f"/v1/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["id"] == task_id

    def test_get_nonexistent_task(self, client: TestClient):
        """Test getting nonexistent task returns 404."""
        response = client.get("/v1/tasks/nonexistent")
        assert response.status_code == 404

    def test_list_tasks(self, client: TestClient):
        """Test listing tasks."""
        # Create a few tasks
        for _ in range(3):
            request = SendMessageRequest(
                message=Message(
                    role=MessageRole.USER,
                    parts=[TextPart(text="Test")],
                ),
            )
            client.post("/v1/message:send", json=request.model_dump())

        response = client.get("/v1/tasks")
        assert response.status_code == 200

        data = response.json()
        assert "tasks" in data
        assert len(data["tasks"]) >= 3


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check(self, client: TestClient):
        """Test health check returns status."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert "agent" in data
        assert "status" in data
        assert data["status"] in ["healthy", "degraded"]
