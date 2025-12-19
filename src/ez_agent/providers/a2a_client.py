"""A2A (Agent-to-Agent) Protocol client for ez-agent.

This module provides a client for making A2A protocol calls to remote agents,
following the official A2A Protocol specification (https://a2a-protocol.org).

The A2A protocol enables agent-to-agent communication using a standard HTTP+JSON
or JSON-RPC binding. This implementation uses the official a2a-sdk Python package.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class A2AToolConfig:
    """Configuration for an A2A tool (remote agent)."""
    
    name: str
    """Name of the tool/agent for identification."""
    
    base_url: str
    """Base URL of the A2A agent endpoint."""
    
    description: str = ""
    """Description of what this agent does."""
    
    headers: dict[str, str] = field(default_factory=dict)
    """Optional headers to include in requests."""


@dataclass
class A2AMessage:
    """A message to send to an A2A agent."""
    
    role: str  # "user" or "agent"
    parts: list[dict[str, Any]]
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    context_id: str | None = None
    task_id: str | None = None
    

@dataclass 
class A2AResponse:
    """Response from an A2A agent."""
    
    content: str
    """Text content of the response."""
    
    task_id: str | None = None
    """Task ID if the agent returned a task."""
    
    context_id: str | None = None
    """Context ID for multi-turn interactions."""
    
    state: str = "completed"
    """Task state (submitted, working, completed, failed, etc.)."""
    
    raw_response: dict[str, Any] = field(default_factory=dict)
    """The full raw response for debugging."""


class A2AClient:
    """
    Client for making A2A protocol calls to remote agents.
    
    Uses the HTTP+JSON/REST protocol binding as defined in the A2A specification:
    - POST /v1/message:send for non-streaming messages
    - POST /v1/message:stream for streaming messages (SSE)
    
    Also supports JSON-RPC binding for servers that prefer that format.
    
    Example usage:
        client = A2AClient()
        response = await client.send_message(
            base_url="https://my-agent.example.com",
            message="Hello, can you help me?",
        )
        print(response.content)
    """
    
    def __init__(
        self,
        timeout: float = 120.0,
        default_headers: dict[str, str] | None = None,
    ):
        """
        Initialize the A2A client.
        
        Args:
            timeout: Request timeout in seconds.
            default_headers: Headers to include in all requests.
        """
        self._timeout = timeout
        self._default_headers = default_headers or {}
    
    async def send_message(
        self,
        base_url: str,
        message: str,
        context_id: str | None = None,
        task_id: str | None = None,
        headers: dict[str, str] | None = None,
        blocking: bool = True,
    ) -> A2AResponse:
        """
        Send a message to an A2A agent and wait for a response.
        
        This method first tries the HTTP+JSON/REST binding (POST /v1/message:send),
        and falls back to JSON-RPC if that fails.
        
        Args:
            base_url: Base URL of the A2A agent (e.g., https://agent.example.com).
            message: Text message to send to the agent.
            context_id: Optional context ID for multi-turn conversations.
            task_id: Optional task ID to continue an existing task.
            headers: Optional additional headers.
            blocking: If True, wait for task completion.
            
        Returns:
            A2AResponse with the agent's response.
            
        Raises:
            A2AError: If the request fails or the agent returns an error.
        """
        merged_headers = {**self._default_headers, **(headers or {})}
        merged_headers.setdefault("Content-Type", "application/json")
        
        # Build the message payload following A2A spec
        message_payload = {
            "role": "user",
            "parts": [{"text": message}],
            "messageId": uuid.uuid4().hex,
        }
        if context_id:
            message_payload["contextId"] = context_id
        if task_id:
            message_payload["taskId"] = task_id
        
        request_payload = {
            "message": message_payload,
            "configuration": {
                "blocking": blocking,
                "acceptedOutputModes": ["text/plain", "application/json"],
            },
        }
        
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            # Try HTTP+JSON/REST binding first
            try:
                response = await self._try_rest_binding(
                    client, base_url, request_payload, merged_headers
                )
                return response
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    # REST endpoint not found, try JSON-RPC
                    logger.debug(f"REST endpoint not found at {base_url}, trying JSON-RPC")
                    return await self._try_jsonrpc_binding(
                        client, base_url, request_payload, merged_headers
                    )
                raise A2AError(f"A2A request failed: {e}") from e
            except Exception as e:
                # Try JSON-RPC as fallback
                logger.debug(f"REST binding failed: {e}, trying JSON-RPC")
                try:
                    return await self._try_jsonrpc_binding(
                        client, base_url, request_payload, merged_headers
                    )
                except Exception as jsonrpc_error:
                    raise A2AError(
                        f"A2A request failed with both REST and JSON-RPC bindings. "
                        f"REST error: {e}, JSON-RPC error: {jsonrpc_error}"
                    ) from jsonrpc_error
    
    async def _try_rest_binding(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> A2AResponse:
        """Try the HTTP+JSON/REST protocol binding."""
        # REST binding: POST /v1/message:send
        url = f"{base_url.rstrip('/')}/v1/message:send"
        
        logger.debug(f"Sending A2A REST request to {url}")
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        return self._parse_response(response.json())
    
    async def _try_jsonrpc_binding(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> A2AResponse:
        """Try the JSON-RPC protocol binding."""
        # JSON-RPC binding: POST to base URL with JSON-RPC envelope
        jsonrpc_payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "SendMessage",
            "params": payload,
        }
        
        logger.debug(f"Sending A2A JSON-RPC request to {base_url}")
        response = await client.post(base_url, json=jsonrpc_payload, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        
        # Handle JSON-RPC response envelope
        if "error" in result and result["error"]:
            error = result["error"]
            raise A2AError(
                f"JSON-RPC error {error.get('code')}: {error.get('message')}"
            )
        
        if "result" in result:
            return self._parse_response(result["result"])
        
        # Some servers return the response directly without JSON-RPC envelope
        return self._parse_response(result)
    
    def _parse_response(self, data: dict[str, Any]) -> A2AResponse:
        """Parse the A2A response into an A2AResponse object."""
        content = ""
        task_id = None
        context_id = None
        state = "completed"
        
        # Check if response is a Task or a direct Message
        if "task" in data:
            # Task response
            task = data["task"]
            task_id = task.get("id")
            context_id = task.get("contextId")
            
            status = task.get("status", {})
            state = status.get("state", "completed")
            
            # Extract content from artifacts or status message
            if "artifacts" in task and task["artifacts"]:
                for artifact in task["artifacts"]:
                    if "parts" in artifact:
                        for part in artifact["parts"]:
                            if "text" in part:
                                content += part["text"]
                            elif isinstance(part, str):
                                content += part
            
            # Fallback to status message if no artifacts
            if not content and "message" in status:
                status_msg = status["message"]
                if status_msg and "parts" in status_msg:
                    for part in status_msg["parts"]:
                        if "text" in part:
                            content += part["text"]
                        elif isinstance(part, str):
                            content += part
                            
        elif "message" in data:
            # Direct Message response (for simple agents)
            msg = data["message"]
            if "parts" in msg:
                for part in msg["parts"]:
                    if "text" in part:
                        content += part["text"]
                    elif isinstance(part, str):
                        content += part
            context_id = msg.get("contextId")
            
        elif "parts" in data:
            # Response is the message itself
            for part in data["parts"]:
                if "text" in part:
                    content += part["text"]
                elif isinstance(part, str):
                    content += part
        
        # Handle case where content is still empty - try to extract from raw
        if not content:
            # Some agents return just text directly
            if isinstance(data.get("text"), str):
                content = data["text"]
            elif isinstance(data.get("result"), str):
                content = data["result"]
        
        return A2AResponse(
            content=content.strip(),
            task_id=task_id,
            context_id=context_id,
            state=state,
            raw_response=data,
        )


class A2AToolExecutor:
    """
    Executor for A2A tools in the context of Azure AI Foundry.
    
    This class manages A2A tool configurations and executes them when
    the model requests an A2A tool call. It acts as a bridge between
    the Azure Agents SDK (which has broken a2a_preview support) and
    the actual A2A protocol implementation.
    """
    
    def __init__(self):
        """Initialize the A2A tool executor."""
        self._tools: dict[str, A2AToolConfig] = {}
        self._client = A2AClient()
        self._contexts: dict[str, str] = {}  # tool_name -> context_id for multi-turn
    
    def register_tool(self, config: A2AToolConfig) -> None:
        """
        Register an A2A tool configuration.
        
        Args:
            config: Tool configuration with name and base URL.
        """
        self._tools[config.name] = config
        logger.info(f"Registered A2A tool: {config.name} -> {config.base_url}")
    
    def get_tool(self, name: str) -> A2AToolConfig | None:
        """Get a registered A2A tool by name."""
        return self._tools.get(name)
    
    def list_tools(self) -> list[A2AToolConfig]:
        """List all registered A2A tools."""
        return list(self._tools.values())
    
    def get_function_definitions(self) -> list[dict[str, Any]]:
        """
        Get function tool definitions for registered A2A tools.
        
        These definitions allow the LLM to "call" A2A tools as if they
        were function tools. The executor will handle routing the call
        to the appropriate A2A agent.
        
        Returns:
            List of function tool definitions in OpenAI-compatible format.
        """
        definitions = []
        for tool in self._tools.values():
            definitions.append({
                "type": "function",
                "function": {
                    "name": f"a2a_{tool.name}",
                    "description": tool.description or f"Send a message to the {tool.name} agent",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": "The message to send to the agent",
                            },
                        },
                        "required": ["message"],
                    },
                },
            })
        return definitions
    
    def is_a2a_tool_call(self, tool_name: str) -> bool:
        """Check if a tool call is for an A2A tool."""
        # A2A tool calls are prefixed with "a2a_"
        if tool_name.startswith("a2a_"):
            actual_name = tool_name[4:]  # Remove "a2a_" prefix
            return actual_name in self._tools
        return tool_name in self._tools
    
    async def execute(
        self,
        tool_name: str,
        arguments: str | dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> str:
        """
        Execute an A2A tool call.
        
        Args:
            tool_name: Name of the tool (with or without "a2a_" prefix).
            arguments: Tool arguments (JSON string or dict).
            headers: Optional headers (e.g., for trace context propagation).
            
        Returns:
            The agent's response as a string.
            
        Raises:
            A2AError: If the tool is not found or execution fails.
        """
        # Handle a2a_ prefix
        actual_name = tool_name[4:] if tool_name.startswith("a2a_") else tool_name
        
        tool = self._tools.get(actual_name)
        if not tool:
            raise A2AError(f"A2A tool not found: {actual_name}")
        
        # Parse arguments
        if isinstance(arguments, str):
            try:
                args = json.loads(arguments)
            except json.JSONDecodeError:
                # Assume the entire string is the message
                args = {"message": arguments}
        else:
            args = arguments
        
        message = args.get("message", "")
        if not message:
            raise A2AError("A2A tool call missing 'message' argument")
        
        # Get context for multi-turn conversations
        context_id = self._contexts.get(actual_name)
        
        # Merge headers
        merged_headers = {**tool.headers, **(headers or {})}
        
        logger.info(f"Executing A2A tool call: {actual_name} -> {tool.base_url}")
        logger.debug(f"Message: {message[:100]}...")
        
        try:
            response = await self._client.send_message(
                base_url=tool.base_url,
                message=message,
                context_id=context_id,
                headers=merged_headers,
            )
            
            # Store context for multi-turn
            if response.context_id:
                self._contexts[actual_name] = response.context_id
            
            logger.info(f"A2A tool response state: {response.state}")
            logger.debug(f"Response content: {response.content[:100]}...")
            
            return response.content
            
        except Exception as e:
            logger.exception(f"A2A tool execution failed: {e}")
            raise A2AError(f"A2A tool execution failed: {e}") from e
    
    def clear(self) -> None:
        """Clear all registered tools and contexts."""
        self._tools.clear()
        self._contexts.clear()


class A2AError(Exception):
    """Error during A2A protocol operations."""
    pass
