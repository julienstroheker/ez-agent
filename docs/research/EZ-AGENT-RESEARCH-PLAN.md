# EZ-Agent Framework: Comprehensive Research & Implementation Plan

**Date:** December 12, 2025  
**Version:** 1.0

---

## Executive Summary

This document provides a comprehensive research summary for building "EZ-Agent", an AI Agent development framework that supports the A2A (Agent-to-Agent) protocol and integrates with Azure AI Foundry. The framework will provide a CLI tool for scaffolding, configuration-driven agent development, and multiple backend provider support.

---

## Table of Contents

1. [A2A Protocol Specification Analysis](#1-a2a-protocol-specification-analysis)
2. [Azure AI Foundry SDK Integration](#2-azure-ai-foundry-sdk-integration)
3. [Python CLI & Configuration Recommendations](#3-python-cli--configuration-recommendations)
4. [Agent Framework Architecture Patterns](#4-agent-framework-architecture-patterns)
5. [Suggested Project Structure](#5-suggested-project-structure)
6. [Key Interfaces for Provider Abstraction](#6-key-interfaces-for-provider-abstraction)
7. [Security Considerations](#7-security-considerations)
8. [Implementation Roadmap](#8-implementation-roadmap)
9. [Azure AI Agents Function Calling Deep Dive](#9-azure-ai-agents-function-calling-deep-dive)

---

## 1. A2A Protocol Specification Analysis

### 1.1 Protocol Overview

The **Agent2Agent (A2A) Protocol** (v1.0 DRAFT) is an open standard enabling communication between independent AI agent systems. Key characteristics:

- **Built on Standards**: HTTP, JSON-RPC 2.0, Server-Sent Events, gRPC
- **Async-First Design**: Native support for long-running tasks and human-in-the-loop
- **Modality Agnostic**: Text, audio/video (via file references), structured data

### 1.2 Core Data Model

#### Task (Primary Unit of Work)
```python
@dataclass
class Task:
    id: str                    # UUID, server-generated
    context_id: str            # Groups related interactions
    status: TaskStatus         # Current status with state
    artifacts: List[Artifact]  # Output artifacts
    history: List[Message]     # Interaction history
    metadata: Dict[str, Any]   # Custom metadata
```

#### TaskState Enumeration
| State | Description |
|-------|-------------|
| `submitted` | Task received, not yet processing |
| `working` | Actively processing |
| `input-required` | Waiting for client input (multi-turn) |
| `completed` | Successfully finished (terminal) |
| `failed` | Error occurred (terminal) |
| `cancelled` | User cancelled (terminal) |
| `rejected` | Agent declined to perform (terminal) |
| `auth-required` | Authentication needed |

#### Message Structure
```python
@dataclass
class Message:
    message_id: str           # UUID, creator-generated
    context_id: Optional[str] # Context association
    task_id: Optional[str]    # Task association
    role: Role                # "user" or "agent"
    parts: List[Part]         # Content container
    metadata: Dict[str, Any]  # Optional metadata
    extensions: List[str]     # Extension URIs
    reference_task_ids: List[str]  # Referenced tasks
```

#### Part Types
- **TextPart**: `{"text": "string content"}`
- **FilePart**: `{"file": {"fileWithUri": "...", "mediaType": "...", "name": "..."}}`
- **DataPart**: `{"data": {...}}` - Structured JSON data

### 1.3 Core Operations (API Endpoints)

#### Method Mapping Reference

| Operation | JSON-RPC | gRPC | HTTP/REST |
|-----------|----------|------|-----------|
| Send Message | `SendMessage` | `SendMessage` | `POST /v1/message:send` |
| Stream Message | `SendStreamingMessage` | `SendStreamingMessage` | `POST /v1/message:stream` |
| Get Task | `GetTask` | `GetTask` | `GET /v1/tasks/{id}` |
| List Tasks | `ListTasks` | `ListTasks` | `GET /v1/tasks` |
| Cancel Task | `CancelTask` | `CancelTask` | `POST /v1/tasks/{id}:cancel` |
| Subscribe to Task | `SubscribeToTask` | `SubscribeToTask` | `POST /v1/tasks/{id}:subscribe` |
| Get Extended Agent Card | `GetExtendedAgentCard` | `GetExtendedAgentCard` | `GET /v1/extendedAgentCard` |

#### SendMessageRequest Structure
```json
{
  "message": {
    "messageId": "uuid",
    "role": "user",
    "parts": [{"text": "Hello"}]
  },
  "configuration": {
    "acceptedOutputModes": ["text/plain", "application/json"],
    "blocking": false,
    "historyLength": 10,
    "pushNotificationConfig": {...}
  },
  "metadata": {}
}
```

### 1.4 Agent Card (Discovery)

The **AgentCard** is a self-describing JSON manifest published at `/.well-known/agent-card.json`:

```json
{
  "protocolVersion": "1.0",
  "name": "My Agent",
  "description": "A helpful agent",
  "supportedInterfaces": [
    {"url": "https://agent.example.com/a2a/v1", "protocolBinding": "HTTP+JSON"}
  ],
  "provider": {
    "organization": "Example Corp",
    "url": "https://example.com"
  },
  "version": "1.0.0",
  "capabilities": {
    "streaming": true,
    "pushNotifications": true,
    "stateTransitionHistory": false,
    "extensions": []
  },
  "securitySchemes": {
    "bearer": {
      "httpAuthSecurityScheme": {
        "scheme": "Bearer",
        "bearerFormat": "JWT"
      }
    }
  },
  "security": [{"bearer": []}],
  "defaultInputModes": ["text/plain", "application/json"],
  "defaultOutputModes": ["text/plain", "application/json"],
  "skills": [
    {
      "id": "general-chat",
      "name": "General Chat",
      "description": "General conversation capabilities",
      "tags": ["chat", "assistant"],
      "examples": ["Hello, how are you?"],
      "inputModes": ["text/plain"],
      "outputModes": ["text/plain"]
    }
  ],
  "supportsExtendedAgentCard": false
}
```

### 1.5 Streaming & Async Patterns

#### Server-Sent Events (SSE) Format
```
data: {"task": {"id": "task-uuid", "status": {"state": "working"}}}

data: {"artifactUpdate": {"taskId": "task-uuid", "artifact": {...}}}

data: {"statusUpdate": {"taskId": "task-uuid", "status": {"state": "completed"}}}
```

#### Push Notifications (Webhooks)
```http
POST {webhook_url}
Authorization: Bearer {credentials}
Content-Type: application/json

{
  "statusUpdate": {
    "taskId": "...",
    "status": {"state": "completed"},
    "final": true
  }
}
```

### 1.6 Error Codes

| Error | JSON-RPC Code | HTTP Status |
|-------|---------------|-------------|
| TaskNotFoundError | -32001 | 404 |
| TaskNotCancelableError | -32002 | 409 |
| PushNotificationNotSupportedError | -32003 | 400 |
| UnsupportedOperationError | -32004 | 400 |
| ContentTypeNotSupportedError | -32005 | 415 |
| InvalidAgentResponseError | -32006 | 502 |
| VersionNotSupportedError | -32009 | 400 |

---

## 2. Azure AI Foundry SDK Integration

### 2.1 SDK Packages

```bash
# Core packages
pip install azure-ai-projects
pip install azure-ai-agents  # Agents functionality
pip install azure-identity   # Authentication

# Optional integrations
pip install langchain-azure-ai  # LangChain integration
pip install semantic-kernel     # Semantic Kernel integration
```

### 2.2 Authentication Methods

#### DefaultAzureCredential (Recommended)
```python
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

credential = DefaultAzureCredential()
client = AIProjectClient(
    endpoint="https://<resource>.ai.azure.com/api/projects/<project>",
    credential=credential
)
```

**Credential Chain Order:**
1. Environment variables (`AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`)
2. Managed Identity (when running in Azure)
3. Azure CLI (`az login`)
4. Visual Studio credentials
5. Azure PowerShell

#### Production Best Practices
```python
from azure.identity import ManagedIdentityCredential, ChainedTokenCredential

# For production - explicit credential chain
credential = ChainedTokenCredential(
    ManagedIdentityCredential(client_id="<user-assigned-mi-id>"),
    # Fallback for local development
)
```

#### Environment Variables
```bash
export AZURE_AI_PROJECT_ENDPOINT="https://<resource>.services.ai.azure.com/api/projects/<project>"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o"
```

### 2.3 Agent Creation Patterns

#### Basic Agent Creation
```python
import os
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

project_client = AIProjectClient(
    endpoint=os.environ["PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential(),
)

with project_client:
    agent = project_client.agents.create_agent(
        model=os.environ["MODEL_DEPLOYMENT_NAME"],
        name="my-agent",
        instructions="You are a helpful assistant.",
    )
    print(f"Created agent with ID: {agent.id}")
```

#### Agent with Tools
```python
from azure.ai.agents.models import (
    CodeInterpreterTool,
    FileSearchTool,
    FunctionTool,
    ToolSet
)

# Create tools
code_interpreter = CodeInterpreterTool()
file_search = FileSearchTool(vector_store_ids=["vs-id"])
functions = FunctionTool(user_functions=[...])

# Create toolset
toolset = ToolSet()
toolset.add(code_interpreter)
toolset.add(file_search)
toolset.add(functions)

# Enable automatic function execution
project_client.agents.enable_auto_function_calls(toolset)

# Create agent with toolset
agent = project_client.agents.create_agent(
    model="gpt-4o",
    name="tool-enabled-agent",
    instructions="You are a helpful assistant with tools.",
    toolset=toolset,
)
```

### 2.4 Thread & Message Management

```python
# Create a conversation thread
thread = project_client.agents.threads.create()

# Add user message
message = project_client.agents.messages.create(
    thread_id=thread.id,
    role="user",
    content="Hello, how are you?",
)

# Run the agent and process
run = project_client.agents.runs.create_and_process(
    thread_id=thread.id,
    agent_id=agent.id
)

# Check status
if run.status == "failed":
    print(f"Error: {run.last_error}")

# Get messages
from azure.ai.agents.models import ListSortOrder
messages = project_client.agents.messages.list(
    thread_id=thread.id,
    order=ListSortOrder.ASCENDING
)
for msg in messages:
    print(f"{msg.role}: {msg.content}")
```

### 2.5 Streaming Responses

```python
# Stream agent responses
async for event in project_client.agents.runs.stream(
    thread_id=thread.id,
    agent_id=agent.id
):
    if event.type == "message":
        print(event.data.content, end="", flush=True)
    elif event.type == "tool_call":
        print(f"Tool call: {event.data.name}")
```

### 2.6 Function Calling Pattern

```python
from azure.ai.agents.models import FunctionTool

# Define functions
def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"Weather in {city}: Sunny, 72°F"

def search_documents(query: str) -> str:
    """Search internal documents."""
    return f"Found 3 results for: {query}"

user_functions = [get_weather, search_documents]

# Create function tool
functions = FunctionTool(user_functions)

# Use with agent
agent = project_client.agents.create_agent(
    model="gpt-4o",
    name="function-agent",
    instructions="Use available functions to help users.",
    tools=functions.definitions,
    tool_resources=functions.resources,
)
```

---

## 3. Python CLI & Configuration Recommendations

### 3.1 Recommended CLI Framework: Typer

**Why Typer?**
- Built on Click with modern Python (type hints)
- Automatic help generation
- Shell completion support
- Async support
- Clean, declarative syntax

```python
import typer
from pathlib import Path

app = typer.Typer(
    name="ez-agent",
    help="EZ-Agent: AI Agent Development Framework"
)

@app.command()
def init(
    name: str = typer.Argument(..., help="Project name"),
    template: str = typer.Option("basic", help="Template type"),
    output: Path = typer.Option(".", help="Output directory"),
):
    """Initialize a new agent project."""
    typer.echo(f"Creating project: {name}")

@app.command()
def serve(
    config: Path = typer.Option("ez-agent.yaml", help="Config file"),
    port: int = typer.Option(8080, help="Server port"),
    reload: bool = typer.Option(False, help="Auto-reload"),
):
    """Start the agent server."""
    pass

@app.command()
def validate(
    config: Path = typer.Argument(..., help="Config file to validate"),
):
    """Validate agent configuration."""
    pass

if __name__ == "__main__":
    app()
```

### 3.2 YAML Configuration

**Recommended Library: Pydantic + PyYAML**

```python
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
import yaml

class ProviderConfig(BaseModel):
    type: str = Field(..., description="Provider type (azure, openai, anthropic)")
    model: str = Field(..., description="Model deployment name")
    endpoint: Optional[str] = None
    api_key_env: Optional[str] = None

class SkillConfig(BaseModel):
    id: str
    name: str
    description: str
    tags: List[str] = []
    examples: List[str] = []

class AgentConfig(BaseModel):
    name: str
    version: str = "1.0.0"
    description: str
    provider: ProviderConfig
    instructions: str
    skills: List[SkillConfig] = []
    tools: List[str] = []
    middleware: List[str] = []

class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    protocol: str = "http+json"  # or "json-rpc", "grpc"

class EZAgentConfig(BaseModel):
    agent: AgentConfig
    server: ServerConfig
    
    @classmethod
    def from_yaml(cls, path: str) -> "EZAgentConfig":
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)
```

**Example Configuration File (ez-agent.yaml):**
```yaml
agent:
  name: "My Assistant"
  version: "1.0.0"
  description: "A helpful AI assistant"
  
  provider:
    type: "azure"
    model: "gpt-4o"
    endpoint: "${AZURE_AI_PROJECT_ENDPOINT}"
  
  instructions: |
    You are a helpful assistant that helps users with their tasks.
    Always be polite and professional.
  
  skills:
    - id: "general-chat"
      name: "General Chat"
      description: "General conversation capabilities"
      tags: ["chat", "assistant"]
      examples:
        - "Hello, how are you?"
        - "What can you help me with?"
    
    - id: "code-help"
      name: "Code Assistance"
      description: "Help with coding tasks"
      tags: ["code", "programming"]
  
  tools:
    - code_interpreter
    - file_search
  
  middleware:
    - logging
    - rate_limiting
    - auth

server:
  host: "0.0.0.0"
  port: 8080
  protocol: "http+json"
```

### 3.3 HTTP Server: FastAPI + Starlette

```python
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

app = FastAPI(title="EZ-Agent A2A Server")

@app.get("/.well-known/agent-card.json")
async def get_agent_card():
    """Return the agent card for discovery."""
    return agent_card

@app.post("/v1/message:send")
async def send_message(request: Request):
    """Handle A2A message/send."""
    body = await request.json()
    result = await agent.process_message(body)
    return result

@app.post("/v1/message:stream")
async def stream_message(request: Request):
    """Handle A2A message/stream with SSE."""
    body = await request.json()
    
    async def event_generator():
        async for event in agent.stream_message(body):
            yield {"data": json.dumps(event)}
    
    return EventSourceResponse(event_generator())

@app.get("/v1/tasks/{task_id}")
async def get_task(task_id: str):
    """Get task status."""
    return await task_store.get(task_id)
```

---

## 4. Agent Framework Architecture Patterns

### 4.1 Middleware Pattern

```python
from abc import ABC, abstractmethod
from typing import Callable, Awaitable

class Middleware(ABC):
    @abstractmethod
    async def __call__(
        self,
        message: Message,
        context: Context,
        next: Callable[[Message, Context], Awaitable[Response]]
    ) -> Response:
        pass

class LoggingMiddleware(Middleware):
    async def __call__(self, message, context, next):
        logger.info(f"Incoming: {message.message_id}")
        response = await next(message, context)
        logger.info(f"Response: {response}")
        return response

class AuthMiddleware(Middleware):
    async def __call__(self, message, context, next):
        if not await self.validate_auth(context):
            raise AuthenticationError("Invalid credentials")
        return await next(message, context)

class RateLimitMiddleware(Middleware):
    async def __call__(self, message, context, next):
        if await self.is_rate_limited(context):
            raise RateLimitError("Rate limit exceeded")
        return await next(message, context)

# Middleware chain execution
class MiddlewareChain:
    def __init__(self, middlewares: List[Middleware], handler: Callable):
        self.middlewares = middlewares
        self.handler = handler
    
    async def execute(self, message: Message, context: Context) -> Response:
        async def build_chain(index: int):
            if index >= len(self.middlewares):
                return await self.handler(message, context)
            return await self.middlewares[index](
                message, context, 
                lambda m, c: build_chain(index + 1)
            )
        return await build_chain(0)
```

### 4.2 Provider Abstraction Pattern

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[Tool]] = None,
        **kwargs
    ) -> CompletionResponse:
        """Generate a completion."""
        pass
    
    @abstractmethod
    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[Tool]] = None,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """Stream a completion."""
        pass

class AzureAIFoundryProvider(LLMProvider):
    """Azure AI Foundry implementation."""
    
    def __init__(self, config: AzureConfig):
        self.client = AIProjectClient(
            endpoint=config.endpoint,
            credential=DefaultAzureCredential()
        )
        self.model = config.model
    
    async def complete(self, messages, tools=None, **kwargs):
        # Implementation using Azure AI Foundry
        pass

class OpenAIProvider(LLMProvider):
    """OpenAI implementation."""
    pass

class AnthropicProvider(LLMProvider):
    """Anthropic implementation."""
    pass

# Provider factory
class ProviderFactory:
    _providers = {
        "azure": AzureAIFoundryProvider,
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
    }
    
    @classmethod
    def create(cls, config: ProviderConfig) -> LLMProvider:
        provider_class = cls._providers.get(config.type)
        if not provider_class:
            raise ValueError(f"Unknown provider: {config.type}")
        return provider_class(config)
```

### 4.3 Tool Execution Pattern (MCP-Compatible)

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List

class Tool(ABC):
    """Base class for agent tools."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        pass
    
    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """JSON Schema for parameters."""
        pass
    
    @abstractmethod
    async def execute(self, **params) -> ToolResult:
        pass

class ToolRegistry:
    """Registry for available tools."""
    
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
    
    def register(self, tool: Tool):
        self._tools[tool.name] = tool
    
    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)
    
    def list_definitions(self) -> List[Dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                }
            }
            for t in self._tools.values()
        ]

class ToolExecutor:
    """Executes tool calls from LLM responses."""
    
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
    
    async def execute(self, tool_calls: List[ToolCall]) -> List[ToolResult]:
        results = []
        for call in tool_calls:
            tool = self.registry.get(call.name)
            if tool:
                result = await tool.execute(**call.arguments)
                results.append(result)
        return results
```

### 4.4 Conversation Thread Management

```python
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
import uuid

@dataclass
class Thread:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    context_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    messages: List[Message] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

class ThreadStore(ABC):
    """Abstract thread storage."""
    
    @abstractmethod
    async def create(self) -> Thread:
        pass
    
    @abstractmethod
    async def get(self, thread_id: str) -> Optional[Thread]:
        pass
    
    @abstractmethod
    async def add_message(self, thread_id: str, message: Message):
        pass
    
    @abstractmethod
    async def get_history(
        self, 
        thread_id: str, 
        limit: Optional[int] = None
    ) -> List[Message]:
        pass

class InMemoryThreadStore(ThreadStore):
    """In-memory implementation for development."""
    
    def __init__(self):
        self._threads: Dict[str, Thread] = {}
    
    async def create(self) -> Thread:
        thread = Thread()
        self._threads[thread.id] = thread
        return thread
    
    async def get(self, thread_id: str) -> Optional[Thread]:
        return self._threads.get(thread_id)
    
    async def add_message(self, thread_id: str, message: Message):
        if thread := self._threads.get(thread_id):
            thread.messages.append(message)
            thread.updated_at = datetime.utcnow()
    
    async def get_history(
        self, 
        thread_id: str, 
        limit: Optional[int] = None
    ) -> List[Message]:
        if thread := self._threads.get(thread_id):
            if limit:
                return thread.messages[-limit:]
            return thread.messages
        return []
```

---

## 5. Suggested Project Structure

```
ez-agent/
├── pyproject.toml
├── README.md
├── LICENSE
│
├── src/
│   └── ez_agent/
│       ├── __init__.py
│       ├── __main__.py              # CLI entry point
│       │
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── main.py              # Typer app
│       │   ├── init.py              # Project initialization
│       │   ├── serve.py             # Server commands
│       │   └── validate.py          # Validation commands
│       │
│       ├── config/
│       │   ├── __init__.py
│       │   ├── models.py            # Pydantic config models
│       │   ├── loader.py            # YAML/env loading
│       │   └── validation.py        # Config validation
│       │
│       ├── core/
│       │   ├── __init__.py
│       │   ├── agent.py             # Core agent implementation
│       │   ├── task.py              # Task management
│       │   ├── message.py           # Message handling
│       │   ├── context.py           # Context management
│       │   └── errors.py            # Error definitions
│       │
│       ├── a2a/
│       │   ├── __init__.py
│       │   ├── protocol.py          # A2A protocol definitions
│       │   ├── server.py            # A2A server (FastAPI)
│       │   ├── client.py            # A2A client for invoking others
│       │   ├── agent_card.py        # Agent card generation
│       │   └── handlers/
│       │       ├── __init__.py
│       │       ├── message.py       # Message handlers
│       │       ├── task.py          # Task handlers
│       │       └── streaming.py     # Streaming handlers
│       │
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── base.py              # Abstract provider
│       │   ├── azure.py             # Azure AI Foundry
│       │   ├── openai.py            # OpenAI
│       │   ├── anthropic.py         # Anthropic
│       │   └── factory.py           # Provider factory
│       │
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── base.py              # Tool base classes
│       │   ├── registry.py          # Tool registry
│       │   ├── executor.py          # Tool execution
│       │   ├── builtin/
│       │   │   ├── __init__.py
│       │   │   ├── code_interpreter.py
│       │   │   ├── file_search.py
│       │   │   └── web_search.py
│       │   └── mcp/
│       │       ├── __init__.py
│       │       └── adapter.py       # MCP tool adapter
│       │
│       ├── middleware/
│       │   ├── __init__.py
│       │   ├── base.py              # Middleware base class
│       │   ├── chain.py             # Middleware chain
│       │   ├── logging.py           # Logging middleware
│       │   ├── auth.py              # Auth middleware
│       │   ├── rate_limit.py        # Rate limiting
│       │   └── tracing.py           # OpenTelemetry tracing
│       │
│       ├── storage/
│       │   ├── __init__.py
│       │   ├── base.py              # Storage abstractions
│       │   ├── memory.py            # In-memory storage
│       │   ├── redis.py             # Redis storage
│       │   └── sqlite.py            # SQLite storage
│       │
│       └── templates/
│           ├── basic/               # Basic agent template
│           │   ├── ez-agent.yaml
│           │   ├── agent.py
│           │   └── README.md
│           ├── azure/               # Azure AI Foundry template
│           │   └── ...
│           └── multi-turn/          # Multi-turn conversation
│               └── ...
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_providers.py
│   │   └── test_tools.py
│   ├── integration/
│   │   ├── test_a2a_server.py
│   │   └── test_azure_provider.py
│   └── e2e/
│       └── test_full_flow.py
│
├── docs/
│   ├── getting-started.md
│   ├── configuration.md
│   ├── providers.md
│   ├── tools.md
│   └── a2a-protocol.md
│
└── examples/
    ├── basic-agent/
    ├── azure-agent/
    ├── multi-turn-chat/
    └── tool-enabled-agent/
```

---

## 6. Key Interfaces for Provider Abstraction

### 6.1 Provider Interface

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class CompletionRequest:
    messages: List[Message]
    model: Optional[str] = None
    tools: Optional[List[ToolDefinition]] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    stream: bool = False

@dataclass
class CompletionResponse:
    content: str
    tool_calls: Optional[List[ToolCall]] = None
    finish_reason: str = "stop"
    usage: Optional[Dict[str, int]] = None

@dataclass
class StreamChunk:
    content: Optional[str] = None
    tool_call_delta: Optional[ToolCallDelta] = None
    finish_reason: Optional[str] = None

class IProvider(ABC):
    """Interface for LLM providers."""
    
    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Generate a completion."""
        pass
    
    @abstractmethod
    async def stream(
        self, 
        request: CompletionRequest
    ) -> AsyncIterator[StreamChunk]:
        """Stream a completion."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check provider availability."""
        pass
```

### 6.2 Agent Interface

```python
class IAgent(ABC):
    """Interface for agent implementations."""
    
    @property
    @abstractmethod
    def agent_card(self) -> AgentCard:
        """Return the agent's A2A card."""
        pass
    
    @abstractmethod
    async def process_message(
        self,
        message: Message,
        context: Context,
    ) -> Union[Task, Message]:
        """Process an incoming message."""
        pass
    
    @abstractmethod
    async def stream_message(
        self,
        message: Message,
        context: Context,
    ) -> AsyncIterator[StreamResponse]:
        """Stream message processing."""
        pass
    
    @abstractmethod
    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get task status."""
        pass
    
    @abstractmethod
    async def cancel_task(self, task_id: str) -> Task:
        """Cancel a running task."""
        pass
```

### 6.3 Tool Interface

```python
class ITool(ABC):
    """Interface for tools."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        pass
    
    @property
    @abstractmethod
    def parameters_schema(self) -> Dict[str, Any]:
        """JSON Schema for parameters."""
        pass
    
    @abstractmethod
    async def execute(
        self, 
        parameters: Dict[str, Any],
        context: Context,
    ) -> ToolResult:
        pass
    
    def to_definition(self) -> ToolDefinition:
        """Convert to A2A/OpenAI tool definition format."""
        return ToolDefinition(
            type="function",
            function=FunctionDefinition(
                name=self.name,
                description=self.description,
                parameters=self.parameters_schema,
            )
        )
```

### 6.4 Storage Interface

```python
class ITaskStore(ABC):
    """Interface for task storage."""
    
    @abstractmethod
    async def create(self, task: Task) -> Task:
        pass
    
    @abstractmethod
    async def get(self, task_id: str) -> Optional[Task]:
        pass
    
    @abstractmethod
    async def update(self, task: Task) -> Task:
        pass
    
    @abstractmethod
    async def list(
        self,
        context_id: Optional[str] = None,
        status: Optional[TaskState] = None,
        page_size: int = 50,
        page_token: Optional[str] = None,
    ) -> Tuple[List[Task], Optional[str]]:
        pass
    
    @abstractmethod
    async def delete(self, task_id: str) -> bool:
        pass

class IThreadStore(ABC):
    """Interface for conversation thread storage."""
    
    @abstractmethod
    async def create(self) -> Thread:
        pass
    
    @abstractmethod
    async def get(self, thread_id: str) -> Optional[Thread]:
        pass
    
    @abstractmethod
    async def add_message(self, thread_id: str, message: Message):
        pass
    
    @abstractmethod
    async def get_history(
        self, 
        thread_id: str, 
        limit: Optional[int] = None
    ) -> List[Message]:
        pass
```

### 6.5 Middleware Interface

```python
class IMiddleware(ABC):
    """Interface for middleware components."""
    
    @abstractmethod
    async def process(
        self,
        message: Message,
        context: Context,
        next_handler: Callable[[Message, Context], Awaitable[Response]]
    ) -> Response:
        pass
    
    @property
    def order(self) -> int:
        """Middleware execution order (lower = earlier)."""
        return 100
```

---

## 7. Security Considerations

### 7.1 Authentication

- **A2A Protocol**: Support multiple auth schemes (Bearer, OAuth2, API Key, OpenID Connect)
- **Azure AI Foundry**: Use managed identities in production, avoid storing credentials
- **Agent Card Security**: Sign agent cards with JWS for authenticity verification

### 7.2 Authorization

- Implement scope-based access control for task operations
- Validate client permissions before returning task data
- Don't distinguish between "not found" and "unauthorized" (prevents enumeration)

### 7.3 Input Validation

```python
from pydantic import BaseModel, validator

class MessageInput(BaseModel):
    message_id: str
    role: str
    parts: List[Part]
    
    @validator("role")
    def validate_role(cls, v):
        if v not in ("user", "agent"):
            raise ValueError("Role must be 'user' or 'agent'")
        return v
    
    @validator("parts")
    def validate_parts(cls, v):
        if not v:
            raise ValueError("At least one part required")
        return v
```

### 7.4 Rate Limiting

```python
from fastapi import Request
from fastapi.responses import JSONResponse

class RateLimiter:
    def __init__(self, requests_per_minute: int = 60):
        self.rpm = requests_per_minute
        self._counters: Dict[str, List[float]] = {}
    
    async def check(self, client_id: str) -> bool:
        now = time.time()
        if client_id not in self._counters:
            self._counters[client_id] = []
        
        # Clean old entries
        self._counters[client_id] = [
            t for t in self._counters[client_id]
            if now - t < 60
        ]
        
        if len(self._counters[client_id]) >= self.rpm:
            return False
        
        self._counters[client_id].append(now)
        return True
```

### 7.5 Webhook Security (Push Notifications)

- Validate webhook URLs (reject private IPs, localhost)
- Include authentication in webhook requests
- Implement retry with exponential backoff
- Use HTTPS for all webhook endpoints

### 7.6 Transport Security

- **Production**: Require TLS 1.3+ for all connections
- **Headers**: Implement HSTS, CORS restrictions
- **Secrets**: Use environment variables or Azure Key Vault

---

## 8. Implementation Roadmap

### Phase 1: Core Foundation (Weeks 1-2)
- [ ] Project scaffolding with pyproject.toml
- [ ] CLI framework with Typer (init, serve, validate)
- [ ] Configuration loading (Pydantic + YAML)
- [ ] Core data models (Task, Message, Part, AgentCard)
- [ ] In-memory storage implementations

### Phase 2: Provider Integration (Weeks 3-4)
- [ ] Provider abstraction layer
- [ ] Azure AI Foundry provider implementation
- [ ] OpenAI provider implementation
- [ ] Provider factory and configuration

### Phase 3: A2A Protocol (Weeks 5-6)
- [ ] FastAPI server with A2A endpoints
- [ ] Agent card generation and serving
- [ ] Message handling (send, stream)
- [ ] Task management (get, list, cancel)
- [ ] SSE streaming implementation

### Phase 4: Tools & Middleware (Weeks 7-8)
- [ ] Tool abstraction and registry
- [ ] Built-in tools (code interpreter, file search)
- [ ] MCP tool adapter
- [ ] Middleware chain implementation
- [ ] Logging, auth, rate limiting middleware

### Phase 5: Production Hardening (Weeks 9-10)
- [ ] Authentication/authorization
- [ ] Redis storage backend
- [ ] OpenTelemetry tracing
- [ ] Comprehensive error handling
- [ ] Health checks and metrics

### Phase 6: Documentation & Examples (Weeks 11-12)
- [ ] User documentation
- [ ] API reference
- [ ] Example projects
- [ ] Tutorial guides
- [ ] Release preparation

---

## Appendix A: Key Dependencies

```toml
[project]
dependencies = [
    # CLI
    "typer>=0.9.0",
    "rich>=13.0.0",
    
    # Configuration
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "pyyaml>=6.0.0",
    
    # HTTP Server
    "fastapi>=0.100.0",
    "uvicorn>=0.23.0",
    "sse-starlette>=1.6.0",
    
    # Azure AI Foundry
    "azure-ai-projects>=1.0.0",
    "azure-ai-agents>=1.0.0",
    "azure-identity>=1.14.0",
    
    # Storage
    "aioredis>=2.0.0",  # Optional
    "aiosqlite>=0.19.0",  # Optional
    
    # Observability
    "opentelemetry-api>=1.20.0",
    "opentelemetry-sdk>=1.20.0",
    "structlog>=23.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
    "httpx>=0.24.0",
    "ruff>=0.1.0",
    "mypy>=1.5.0",
]
```

---

## Appendix B: Example Agent Implementation

```python
# examples/basic-agent/agent.py
from ez_agent import Agent, AgentConfig
from ez_agent.providers import AzureProvider
from ez_agent.tools import CodeInterpreterTool

config = AgentConfig.from_yaml("ez-agent.yaml")

agent = Agent(
    config=config,
    provider=AzureProvider(config.provider),
    tools=[
        CodeInterpreterTool(),
    ],
)

if __name__ == "__main__":
    agent.serve()
```

---

## 9. Azure AI Agents Function Calling Deep Dive

**Research Date:** December 12, 2025

This section provides a comprehensive analysis of Azure AI Agents function calling, specifically targeting the implementation of a generic tool execution system for the EZ-Agent framework where tools are local Python functions.

### 9.1 Overview

Azure AI Agents supports function calling, which allows you to:
1. Define the structure of functions (tools) that an agent can call
2. Register these functions with an agent during creation
3. Handle function call requests from the model
4. Execute local Python code and return results back to the agent

**Important Constraints:**
- Runs expire **10 minutes** after creation - tool outputs must be submitted before expiration
- Function calling is NOT supported in the Microsoft Foundry portal UI (agents appear but won't perform function calling when run from portal)

### 9.2 SDK Classes and Imports

The primary classes for function calling in the `azure-ai-agents` SDK:

```python
# Core imports for function calling
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import (
    FunctionTool,          # Wraps user functions for agent use
    ToolSet,               # Container for multiple tools
    AsyncFunctionTool,     # Async version of FunctionTool
    AsyncToolSet,          # Async version of ToolSet
)
from azure.identity import DefaultAzureCredential
from typing import Set, Callable, Any
```

### 9.3 Function Definition Patterns

Functions must have descriptive docstrings that the SDK uses to generate JSON schemas. The SDK introspects:
- Function name
- Parameters (names, types from type hints)
- Docstring (used for description)
- Return type

#### Basic Function Definition

```python
import json

def fetch_weather(location: str) -> str:
    """
    Fetches the weather information for the specified location.

    :param location: The location to fetch weather for.
    :return: Weather information as a JSON string.
    """
    # Mock implementation
    mock_weather_data = {
        "New York": "Sunny, 25°C",
        "London": "Cloudy, 18°C", 
        "Tokyo": "Rainy, 22°C"
    }
    weather = mock_weather_data.get(
        location, 
        "Weather data not available for this location."
    )
    return json.dumps({"weather": weather})

def get_current_datetime() -> str:
    """
    Gets the current date and time.
    
    :return: Current datetime as a string.
    """
    from datetime import datetime
    return datetime.now().isoformat()

# Collect functions in a set
user_functions: Set[Callable[..., Any]] = {
    fetch_weather,
    get_current_datetime,
}
```

#### Enhanced Function Definition with Pydantic (Agent Framework Pattern)

For more control over function descriptions, use type annotations:

```python
from typing import Annotated
from pydantic import Field

def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    return f"The weather in {location} is cloudy with a high of 15°C."
```

### 9.4 FunctionTool Class

`FunctionTool` wraps Python functions and generates tool definitions:

```python
from azure.ai.agents.models import FunctionTool

# Create FunctionTool from user functions
functions = FunctionTool(functions=user_functions)

# Key properties:
# - functions.definitions  -> List of tool definitions for agent creation
# - functions.resources    -> Tool resources (if applicable)
```

The `FunctionTool` class automatically:
1. Parses function signatures using Python introspection
2. Extracts parameter types from type hints
3. Parses docstrings for descriptions
4. Generates JSON Schema for parameters

### 9.5 Agent Creation with Function Tools

#### Method 1: Using `tools` parameter directly

```python
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import FunctionTool
from azure.identity import DefaultAzureCredential

project_client = AIProjectClient(
    endpoint=os.environ["PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential()
)

# Initialize FunctionTool
functions = FunctionTool(functions=user_functions)

with project_client:
    # Create agent with function tools
    agent = project_client.agents.create_agent(
        model=os.environ["MODEL_DEPLOYMENT_NAME"],
        name="my-agent",
        instructions="You are a helpful agent. Use available functions.",
        tools=functions.definitions,  # Pass tool definitions
    )
    print(f"Created agent, ID: {agent.id}")
```

#### Method 2: Using ToolSet (recommended for multiple tool types)

```python
from azure.ai.agents.models import FunctionTool, ToolSet, CodeInterpreterTool

# Create individual tools
functions = FunctionTool(user_functions)
code_interpreter = CodeInterpreterTool()

# Combine in ToolSet
toolset = ToolSet()
toolset.add(functions)
toolset.add(code_interpreter)

# Create agent with toolset
agent = project_client.agents.create_agent(
    model=os.environ["MODEL_DEPLOYMENT_NAME"],
    name="my-agent",
    instructions="You are a helpful agent",
    toolset=toolset,  # Pass entire toolset
)
```

### 9.6 Execution Flow: Manual Function Handling

This is the **critical pattern for EZ-Agent** - manual handling of function calls allows full control over execution:

```python
import time
import json

# Step 1: Create thread for communication
thread = project_client.agents.threads.create()

# Step 2: Add user message
message = project_client.agents.messages.create(
    thread_id=thread.id,
    role="user",
    content="What's the weather in New York?",
)

# Step 3: Create a run
run = project_client.agents.runs.create(
    thread_id=thread.id, 
    agent_id=agent.id
)

# Step 4: Poll and handle function calls
while run.status in ["queued", "in_progress", "requires_action"]:
    time.sleep(1)
    run = project_client.agents.runs.get(
        thread_id=thread.id, 
        run_id=run.id
    )

    # Check if function calling is required
    if run.status == "requires_action":
        # Extract tool calls from the run
        tool_calls = run.required_action.submit_tool_outputs.tool_calls
        tool_outputs = []
        
        for tool_call in tool_calls:
            # Get function name and arguments
            function_name = tool_call.function.name
            arguments_json = tool_call.function.arguments  # JSON string
            arguments = json.loads(arguments_json)
            
            # Execute the appropriate function
            if function_name == "fetch_weather":
                output = fetch_weather(arguments["location"])
            elif function_name == "get_current_datetime":
                output = get_current_datetime()
            else:
                output = json.dumps({"error": f"Unknown function: {function_name}"})
            
            # Collect outputs with tool_call_id for correlation
            tool_outputs.append({
                "tool_call_id": tool_call.id,
                "output": output
            })
        
        # Submit all tool outputs back to the run
        project_client.agents.runs.submit_tool_outputs(
            thread_id=thread.id, 
            run_id=run.id, 
            tool_outputs=tool_outputs
        )

print(f"Run completed with status: {run.status}")

# Step 5: Retrieve final messages
messages = project_client.agents.messages.list(thread_id=thread.id)
for msg in messages:
    print(f"Role: {msg['role']}, Content: {msg['content']}")
```

### 9.7 Automatic Function Calling

For simpler use cases, the SDK can handle function execution automatically:

```python
# Enable auto function calls on the toolset
agents_client.enable_auto_function_calls(toolset)

# Now create_and_process or streaming will auto-execute functions
run = agents_client.runs.create_and_process(
    thread_id=thread.id, 
    agent_id=agent.id
)

# Functions in the toolset are automatically invoked by the SDK
```

**When to use auto vs manual:**
- **Auto**: Simple functions, no error handling needed, trust SDK execution
- **Manual**: Custom error handling, logging, validation, async execution, sandboxing

### 9.8 Async Function Execution

For async functions, use `AsyncFunctionTool`:

```python
from azure.ai.agents.aio import AgentsClient  # Note: async import
from azure.ai.agents.models import AsyncFunctionTool, AsyncToolSet

# Define async functions
async def async_fetch_weather(location: str) -> str:
    """Fetches weather asynchronously."""
    await asyncio.sleep(0.1)  # Simulate async operation
    return json.dumps({"weather": "Sunny", "location": location})

async def async_search_database(query: str) -> str:
    """Searches database asynchronously."""
    await asyncio.sleep(0.2)
    return json.dumps({"results": ["item1", "item2"], "query": query})

user_async_functions = {async_fetch_weather, async_search_database}

# Create async tools
functions = AsyncFunctionTool(user_async_functions)
toolset = AsyncToolSet()
toolset.add(functions)

# Enable auto function calls
agents_client.enable_auto_function_calls(toolset)

# Create agent asynchronously
agent = await agents_client.create_agent(
    model=os.environ["MODEL_DEPLOYMENT_NAME"],
    name="my-async-agent",
    instructions="You are a helpful agent",
    toolset=toolset,
)
```

### 9.9 Tool Call Data Structures

Understanding the data structures is crucial for implementing a generic executor:

#### Run Status States
| Status | Description |
|--------|-------------|
| `queued` | Run is queued for processing |
| `in_progress` | Run is actively processing |
| `requires_action` | **Function call needed** - must submit tool outputs |
| `completed` | Run finished successfully |
| `failed` | Run failed with error |
| `cancelled` | Run was cancelled |
| `expired` | Run expired (10 min limit) |

#### Required Action Structure

```python
# When run.status == "requires_action":
run.required_action.submit_tool_outputs.tool_calls  # List of tool calls

# Each tool_call has:
tool_call.id             # Unique ID for this call (required for response)
tool_call.type           # "function"
tool_call.function.name  # Function name to call
tool_call.function.arguments  # JSON string of arguments
```

#### Tool Output Structure

```python
tool_output = {
    "tool_call_id": tool_call.id,  # MUST match the tool_call.id
    "output": "string result"       # Must be a string (JSON recommended)
}
```

### 9.10 Error Handling Best Practices

```python
import traceback

def safe_execute_function(function_name: str, arguments: dict) -> str:
    """Safely execute a function with error handling."""
    try:
        # Look up function
        func = FUNCTION_REGISTRY.get(function_name)
        if func is None:
            return json.dumps({
                "error": f"Unknown function: {function_name}",
                "available_functions": list(FUNCTION_REGISTRY.keys())
            })
        
        # Validate arguments (optional - use pydantic or similar)
        # ...
        
        # Execute function
        result = func(**arguments)
        
        # Ensure result is string
        if not isinstance(result, str):
            result = json.dumps(result)
        
        return result
        
    except TypeError as e:
        # Argument mismatch
        return json.dumps({
            "error": "Invalid arguments",
            "message": str(e),
            "function": function_name
        })
    except Exception as e:
        # General error
        return json.dumps({
            "error": "Function execution failed",
            "message": str(e),
            "traceback": traceback.format_exc()
        })

# Usage in the polling loop:
for tool_call in tool_calls:
    arguments = json.loads(tool_call.function.arguments)
    output = safe_execute_function(
        tool_call.function.name, 
        arguments
    )
    tool_outputs.append({
        "tool_call_id": tool_call.id,
        "output": output
    })
```

### 9.11 Generic Tool Executor Design for EZ-Agent

Based on this research, here's a recommended design for EZ-Agent's tool system:

```python
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Set, Optional
from dataclasses import dataclass
import json
import inspect
from pydantic import BaseModel, create_model

@dataclass
class ToolDefinition:
    """Tool definition for agent registration."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema
    function: Callable

class ToolRegistry:
    """Registry of available tools."""
    
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
    
    def register(self, func: Callable) -> ToolDefinition:
        """Register a Python function as a tool."""
        # Extract metadata from function
        name = func.__name__
        description = func.__doc__ or f"Function: {name}"
        
        # Build parameter schema from signature
        sig = inspect.signature(func)
        parameters = self._build_parameter_schema(sig, func)
        
        tool = ToolDefinition(
            name=name,
            description=description.strip(),
            parameters=parameters,
            function=func
        )
        self._tools[name] = tool
        return tool
    
    def _build_parameter_schema(
        self, 
        sig: inspect.Signature, 
        func: Callable
    ) -> Dict[str, Any]:
        """Build JSON Schema from function signature."""
        properties = {}
        required = []
        
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
                
            # Map Python types to JSON Schema types
            param_type = param.annotation
            json_type = self._python_to_json_type(param_type)
            
            properties[param_name] = {
                "type": json_type,
                "description": f"Parameter: {param_name}"  # Could parse from docstring
            }
            
            if param.default is inspect.Parameter.empty:
                required.append(param_name)
        
        return {
            "type": "object",
            "properties": properties,
            "required": required
        }
    
    def _python_to_json_type(self, python_type) -> str:
        """Map Python type to JSON Schema type."""
        type_map = {
            str: "string",
            int: "integer", 
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }
        return type_map.get(python_type, "string")
    
    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get tool by name."""
        return self._tools.get(name)
    
    def execute(self, name: str, arguments: Dict[str, Any]) -> str:
        """Execute a tool by name with given arguments."""
        tool = self._tools.get(name)
        if tool is None:
            return json.dumps({"error": f"Unknown tool: {name}"})
        
        try:
            result = tool.function(**arguments)
            if not isinstance(result, str):
                result = json.dumps(result)
            return result
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    def get_azure_function_tool(self) -> "FunctionTool":
        """Convert registry to Azure FunctionTool."""
        from azure.ai.agents.models import FunctionTool
        return FunctionTool(functions=set(t.function for t in self._tools.values()))

# Decorator for easy registration
def tool(registry: ToolRegistry):
    """Decorator to register a function as a tool."""
    def decorator(func: Callable) -> Callable:
        registry.register(func)
        return func
    return decorator

# Usage example:
registry = ToolRegistry()

@tool(registry)
def search_documents(query: str, max_results: int = 10) -> str:
    """
    Search internal documents for relevant information.
    
    :param query: The search query string.
    :param max_results: Maximum number of results to return.
    :return: JSON string of search results.
    """
    # Implementation
    return json.dumps({"results": [], "query": query})

@tool(registry)
def get_user_info(user_id: str) -> str:
    """
    Retrieve information about a user.
    
    :param user_id: The unique identifier for the user.
    :return: JSON string with user information.
    """
    return json.dumps({"user_id": user_id, "name": "John Doe"})
```

### 9.12 Complete Execution Loop for EZ-Agent

```python
class AgentExecutor:
    """Executes agent runs with tool handling."""
    
    def __init__(
        self, 
        agents_client, 
        tool_registry: ToolRegistry,
        poll_interval: float = 1.0,
        max_iterations: int = 10
    ):
        self.agents_client = agents_client
        self.tool_registry = tool_registry
        self.poll_interval = poll_interval
        self.max_iterations = max_iterations
    
    async def execute(
        self, 
        agent_id: str, 
        thread_id: str, 
        message: str
    ) -> Dict[str, Any]:
        """Execute a full agent run with tool handling."""
        
        # Add user message
        await self.agents_client.messages.create(
            thread_id=thread_id,
            role="user",
            content=message
        )
        
        # Create run
        run = await self.agents_client.runs.create(
            thread_id=thread_id,
            agent_id=agent_id
        )
        
        iterations = 0
        while run.status in ["queued", "in_progress", "requires_action"]:
            if iterations >= self.max_iterations:
                raise RuntimeError("Max iterations exceeded")
            
            await asyncio.sleep(self.poll_interval)
            run = await self.agents_client.runs.get(
                thread_id=thread_id,
                run_id=run.id
            )
            
            if run.status == "requires_action":
                await self._handle_tool_calls(thread_id, run)
            
            iterations += 1
        
        if run.status == "failed":
            raise RuntimeError(f"Run failed: {run.last_error}")
        
        # Get final messages
        messages = await self.agents_client.messages.list(thread_id=thread_id)
        return {"status": run.status, "messages": list(messages)}
    
    async def _handle_tool_calls(self, thread_id: str, run) -> None:
        """Handle tool calls from the model."""
        tool_calls = run.required_action.submit_tool_outputs.tool_calls
        tool_outputs = []
        
        for tool_call in tool_calls:
            name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
            
            # Execute tool
            output = self.tool_registry.execute(name, arguments)
            
            tool_outputs.append({
                "tool_call_id": tool_call.id,
                "output": output
            })
        
        # Submit outputs
        await self.agents_client.runs.submit_tool_outputs(
            thread_id=thread_id,
            run_id=run.id,
            tool_outputs=tool_outputs
        )
```

### 9.13 Key Takeaways for EZ-Agent Implementation

1. **FunctionTool introspects Python functions** - Use docstrings and type hints for schema generation

2. **Manual execution gives control** - For EZ-Agent, manual handling is recommended for:
   - Custom error handling
   - Logging and observability  
   - Validation before execution
   - Timeout handling

3. **tool_call_id is critical** - Each output MUST be correlated with the correct tool_call.id

4. **Outputs must be strings** - Convert all results to JSON strings

5. **10-minute timeout** - Runs expire; implement appropriate timeout handling

6. **Async support is native** - Use `AsyncFunctionTool` and `AsyncToolSet` for async functions

7. **ToolSet for composition** - Combine multiple tool types (functions, code interpreter, etc.)

8. **Enable auto-execution when appropriate** - Use `enable_auto_function_calls()` for simple cases

### 9.14 References for Function Calling

- **Azure AI Agents SDK Reference**: https://learn.microsoft.com/en-us/python/api/overview/azure/ai-agents-readme
- **Function Calling Guide**: https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/function-calling
- **SDK Samples (GitHub)**: 
  - `sample_agents_functions.py` - Manual function handling
  - `sample_agents_auto_function_call.py` - Automatic execution
  - `sample_agents_stream_eventhandler_with_functions.py` - Streaming with functions

---

## Appendix C: References

1. **A2A Protocol Specification**: https://a2a-protocol.org/latest/specification/
2. **Azure AI Foundry Documentation**: https://learn.microsoft.com/en-us/azure/ai-foundry/
3. **Azure AI Projects SDK**: https://learn.microsoft.com/en-us/python/api/overview/azure/ai-projects-readme
4. **Azure AI Agents SDK**: https://learn.microsoft.com/en-us/python/api/overview/azure/ai-agents-readme
5. **Azure AI Agents Function Calling**: https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/function-calling
6. **FastAPI Documentation**: https://fastapi.tiangolo.com/
7. **Typer Documentation**: https://typer.tiangolo.com/
8. **Pydantic Documentation**: https://docs.pydantic.dev/
