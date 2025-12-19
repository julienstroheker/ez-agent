"""A2A protocol FastAPI server implementation."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from ez_agent.a2a.models import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    ErrorResponse,
    ListTasksResponse,
    Message,
    MessageRole,
    SendMessageRequest,
    SendMessageResponse,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)
from ez_agent.core.agent import Agent
from ez_agent.runtime.factory import create_agent_from_config
from ez_agent.storage.base import TaskData

if TYPE_CHECKING:
    from ez_agent.config.models import AgentConfig

logger = logging.getLogger(__name__)


def create_app(config: "AgentConfig") -> FastAPI:
    """
    Create a FastAPI application for the A2A protocol.

    Args:
        config: Agent configuration.

    Returns:
        Configured FastAPI application.
    """
    # Store agent in app state
    agent_instance: Agent | None = None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal agent_instance
        # Startup
        logger.info(f"Starting A2A server for agent: {config.name}")
        agent_instance = create_agent_from_config(config)
        app.state.agent = agent_instance
        app.state.config = config
        yield
        # Shutdown
        if agent_instance:
            await agent_instance.close()
        logger.info("A2A server stopped")

    app = FastAPI(
        title=f"{config.name} - A2A Agent",
        description=config.description,
        version=config.version,
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure based on deployment needs
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    _register_routes(app)

    return app


def _register_routes(app: FastAPI) -> None:
    """Register all A2A protocol routes."""

    @app.get("/.well-known/agent-card.json", response_model=AgentCard)
    async def get_agent_card(request: Request) -> AgentCard:
        """Return the agent card for discovery."""
        config = request.app.state.config
        agent = request.app.state.agent

        # Build base URL
        base_url = str(request.base_url).rstrip("/")

        # Build skills from tools
        skills: list[AgentSkill] = []
        
        # Add skills from tool registry (Python function tools)
        if agent._tool_registry:
            for tool_name in agent._tool_registry.list_tools():
                tool = agent._tool_registry.get(tool_name)
                if tool:
                    skills.append(AgentSkill(
                        id=tool_name,
                        name=tool_name,
                        description=tool.description,
                    ))
        
        # Add skills from config tools (MCP, A2A, HTTP tools)
        for tool_config in config.tools:
            # Skip function tools (already added from registry)
            if tool_config.type == "function":
                continue
            
            # Build skill ID based on tool type
            if tool_config.type == "agent":
                skill_id = f"a2a_{tool_config.name}"
            elif tool_config.type == "mcp":
                skill_id = f"mcp_{tool_config.server_label or tool_config.name}"
            else:
                skill_id = tool_config.name
            
            skills.append(AgentSkill(
                id=skill_id,
                name=tool_config.name,
                description=tool_config.description or f"{tool_config.type} tool: {tool_config.name}",
            ))

        return AgentCard(
            name=config.name,
            description=config.description,
            version=config.version,
            url=base_url,
            capabilities=AgentCapabilities(
                streaming=config.features.streaming,
                pushNotifications=False,
                stateTransitionHistory=True,
            ),
            skills=skills,
        )

    @app.post("/v1/message:send", response_model=SendMessageResponse)
    async def send_message(
        request: Request,
        body: SendMessageRequest,
    ) -> SendMessageResponse:
        """Send a message to the agent (synchronous)."""
        agent: Agent = request.app.state.agent

        # Extract text content from message
        text_content = _extract_text_from_message(body.message)
        if not text_content:
            raise HTTPException(
                status_code=400,
                detail="Message must contain text content",
            )

        try:
            # Process the message
            task_data, response_text = await agent.process_message(
                message=text_content,
                session_id=body.sessionId,
                metadata=body.metadata,
            )

            # Convert to A2A task
            a2a_task = _task_data_to_a2a(task_data)

            return SendMessageResponse(task=a2a_task)

        except Exception as e:
            logger.exception(f"Error processing message: {e}")
            raise HTTPException(
                status_code=500,
                detail=str(e),
            )

    @app.post("/v1/message:stream")
    async def stream_message(
        request: Request,
        body: SendMessageRequest,
    ) -> EventSourceResponse:
        """Send a message to the agent with streaming response (SSE)."""
        agent: Agent = request.app.state.agent

        # Extract text content
        text_content = _extract_text_from_message(body.message)
        if not text_content:
            raise HTTPException(
                status_code=400,
                detail="Message must contain text content",
            )

        async def event_generator() -> AsyncIterator[dict[str, Any]]:
            try:
                async for task_data, chunk in agent.stream_message(
                    message=text_content,
                    session_id=body.sessionId,
                    metadata=body.metadata,
                ):
                    # Send content chunks
                    if chunk.content:
                        yield {
                            "event": "message",
                            "data": json.dumps({
                                "type": "content",
                                "content": chunk.content,
                            }),
                        }

                    # Send tool call info
                    for tool_call in chunk.tool_calls:
                        yield {
                            "event": "message",
                            "data": json.dumps({
                                "type": "tool_call",
                                "tool": tool_call.name,
                                "arguments": tool_call.arguments,
                            }),
                        }

                    # Send completion
                    if chunk.is_final:
                        a2a_task = _task_data_to_a2a(task_data)
                        yield {
                            "event": "done",
                            "data": json.dumps({
                                "task": a2a_task.model_dump(),
                            }),
                        }

            except Exception as e:
                logger.exception(f"Stream error: {e}")
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "error": str(e),
                        "code": "internal_error",
                    }),
                }

        return EventSourceResponse(event_generator())

    @app.get("/v1/tasks/{task_id}", response_model=Task)
    async def get_task(
        request: Request,
        task_id: str,
    ) -> Task:
        """Get a task by ID."""
        agent: Agent = request.app.state.agent

        task_data = await agent.get_task(task_id)
        if not task_data:
            raise HTTPException(
                status_code=404,
                detail=f"Task {task_id} not found",
            )

        return _task_data_to_a2a(task_data)

    @app.post("/v1/tasks/{task_id}:cancel", response_model=Task)
    async def cancel_task(
        request: Request,
        task_id: str,
    ) -> Task:
        """Cancel a running task."""
        agent: Agent = request.app.state.agent

        try:
            task_data = await agent.cancel_task(task_id)
            return _task_data_to_a2a(task_data)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=str(e),
            )

    @app.get("/v1/tasks", response_model=ListTasksResponse)
    async def list_tasks(
        request: Request,
        session_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> ListTasksResponse:
        """List tasks with optional filtering."""
        agent: Agent = request.app.state.agent

        tasks = await agent.list_tasks(
            session_id=session_id,
            limit=limit,
        )

        a2a_tasks = [_task_data_to_a2a(t) for t in tasks]

        return ListTasksResponse(
            tasks=a2a_tasks,
            total=len(a2a_tasks),
        )

    @app.get("/health")
    async def health_check(request: Request) -> dict[str, Any]:
        """Health check endpoint."""
        agent: Agent = request.app.state.agent
        return await agent.health_check()

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        """Handle HTTP exceptions with A2A error format."""
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=exc.detail,
                code=f"http_{exc.status_code}",
            ).model_dump(),
        )


def _extract_text_from_message(message: Message) -> str | None:
    """Extract text content from a message."""
    for part in message.parts:
        if isinstance(part, TextPart):
            return part.text
        elif hasattr(part, "text"):
            return part.text
    return None


def _task_data_to_a2a(task_data: TaskData) -> Task:
    """Convert internal TaskData to A2A Task model."""
    # Map internal status to A2A state
    state_mapping = {
        "submitted": TaskState.SUBMITTED,
        "working": TaskState.WORKING,
        "input-required": TaskState.INPUT_REQUIRED,
        "completed": TaskState.COMPLETED,
        "failed": TaskState.FAILED,
        "cancelled": TaskState.CANCELLED,
        "rejected": TaskState.REJECTED,
    }

    state = state_mapping.get(task_data.status.value, TaskState.SUBMITTED)

    # Convert messages
    messages: list[Message] = []
    for msg in task_data.messages:
        role = MessageRole.USER if msg.role == "user" else MessageRole.AGENT
        parts = []
        for part in msg.parts:
            if part.type == "text" and isinstance(part.content, str):
                parts.append(TextPart(text=part.content))

        if parts:
            messages.append(Message(role=role, parts=parts))

    return Task(
        id=task_data.id,
        sessionId=task_data.session_id,
        status=TaskStatus(
            state=state,
            message=task_data.error,
            timestamp=task_data.updated_at,
        ),
        messages=messages,
        artifacts=[],  # TODO: Convert artifacts
        metadata=task_data.metadata,
    )
