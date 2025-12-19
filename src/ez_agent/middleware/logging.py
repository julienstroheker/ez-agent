"""Logging middleware."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from ez_agent.middleware.base import IMiddleware, MiddlewareContext, NextHandler

if TYPE_CHECKING:
    from ez_agent.core.agent import AgentContext
    from ez_agent.providers.base import ProviderResponse


logger = logging.getLogger(__name__)


class LoggingMiddleware(IMiddleware):
    """
    Middleware that logs request/response details.

    Logs:
    - Request start with task ID and message preview
    - Request completion with duration
    - Errors with stack traces
    """

    def __init__(
        self,
        log_level: int = logging.INFO,
        include_content: bool = False,
        max_content_length: int = 100,
    ) -> None:
        """
        Initialize logging middleware.

        Args:
            log_level: Log level to use.
            include_content: Whether to include message content in logs.
            max_content_length: Max characters to log for content.
        """
        self._log_level = log_level
        self._include_content = include_content
        self._max_content_length = max_content_length

    @property
    def name(self) -> str:
        """Return the middleware name."""
        return "logging"

    async def process(
        self,
        context: "AgentContext",
        middleware_context: MiddlewareContext,
        next_handler: NextHandler,
    ) -> "ProviderResponse":
        """Log request and response."""
        start_time = time.time()
        middleware_context.start_time = start_time

        # Log request start
        task_id = context.task.id
        request_id = context.request_id
        message_count = len(context.messages)

        log_msg = f"[{request_id}] Processing task {task_id} with {message_count} messages"

        if self._include_content and context.messages:
            last_msg = context.messages[-1]
            content_preview = last_msg.content[:self._max_content_length]
            if len(last_msg.content) > self._max_content_length:
                content_preview += "..."
            log_msg += f" | Content: {content_preview}"

        logger.log(self._log_level, log_msg)

        try:
            # Call next handler
            response = await next_handler(context)

            # Log success
            duration = time.time() - start_time
            response_preview = ""
            if self._include_content and response.content:
                response_preview = response.content[:self._max_content_length]
                if len(response.content) > self._max_content_length:
                    response_preview += "..."
                response_preview = f" | Response: {response_preview}"

            tool_info = ""
            if response.tool_calls:
                tool_names = [tc.name for tc in response.tool_calls]
                tool_info = f" | Tools: {tool_names}"

            logger.log(
                self._log_level,
                f"[{request_id}] Completed task {task_id} in {duration:.2f}s"
                f"{tool_info}{response_preview}",
            )

            return response

        except Exception as e:
            duration = time.time() - start_time
            logger.exception(
                f"[{request_id}] Failed task {task_id} after {duration:.2f}s: {e}"
            )
            raise
