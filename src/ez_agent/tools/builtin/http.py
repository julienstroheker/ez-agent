"""HTTP tool for making API calls."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from ez_agent.tools.base import ITool, ToolDefinition, ToolError, ToolParameter

logger = logging.getLogger(__name__)


class HttpTool(ITool):
    """
    Tool for making HTTP requests.

    Supports GET, POST, PUT, PATCH, DELETE methods.
    """

    def __init__(
        self,
        name: str,
        description: str,
        endpoint: str,
        method: str = "POST",
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        """
        Initialize HTTP tool.

        Args:
            name: Tool name.
            description: Tool description.
            endpoint: Base endpoint URL.
            method: HTTP method.
            headers: Default headers.
            timeout: Request timeout in seconds.
        """
        self._name = name
        self._description = description
        self._endpoint = endpoint
        self._method = method.upper()
        self._headers = headers or {}
        self._timeout = timeout

    @property
    def name(self) -> str:
        """Return the tool name."""
        return self._name

    @property
    def description(self) -> str:
        """Return the tool description."""
        return self._description

    def get_definition(self) -> ToolDefinition:
        """Get the tool definition."""
        parameters = [
            ToolParameter(
                name="body",
                type="object",
                description="Request body (for POST/PUT/PATCH)",
                required=False,
            ),
            ToolParameter(
                name="query_params",
                type="object",
                description="Query parameters",
                required=False,
            ),
            ToolParameter(
                name="path_params",
                type="object",
                description="Path parameters to substitute in the URL",
                required=False,
            ),
        ]

        return ToolDefinition(
            name=self._name,
            description=self._description,
            parameters=parameters,
        )

    async def execute(
        self,
        body: dict[str, Any] | None = None,
        query_params: dict[str, str] | None = None,
        path_params: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> str:
        """Execute the HTTP request."""
        # Build URL with path parameters
        url = self._endpoint
        if path_params:
            for key, value in path_params.items():
                url = url.replace(f"{{{key}}}", str(value))

        logger.debug(f"HTTP {self._method} {url}")

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(
                    method=self._method,
                    url=url,
                    headers=self._headers,
                    params=query_params,
                    json=body if self._method in ("POST", "PUT", "PATCH") else None,
                )

                # Try to parse as JSON, fall back to text
                try:
                    result = response.json()
                except json.JSONDecodeError:
                    result = {"text": response.text, "status_code": response.status_code}

                if not response.is_success:
                    result["error"] = True
                    result["status_code"] = response.status_code

                return json.dumps(result)

        except httpx.TimeoutException as e:
            raise ToolError(
                message=f"Request timed out after {self._timeout}s",
                tool_name=self._name,
                cause=e,
            )
        except httpx.RequestError as e:
            raise ToolError(
                message=f"Request failed: {e}",
                tool_name=self._name,
                cause=e,
            )
