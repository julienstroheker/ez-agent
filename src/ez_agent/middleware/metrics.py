"""Metrics middleware for monitoring."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ez_agent.middleware.base import IMiddleware, MiddlewareContext, NextHandler

if TYPE_CHECKING:
    from ez_agent.core.agent import AgentContext
    from ez_agent.providers.base import ProviderResponse


logger = logging.getLogger(__name__)


@dataclass
class RequestMetrics:
    """Metrics for a single request."""

    task_id: str
    request_id: str
    start_time: float
    end_time: float | None = None
    duration_ms: float | None = None
    status: str = "unknown"
    tool_calls: int = 0
    error: str | None = None


@dataclass
class AggregateMetrics:
    """Aggregate metrics over multiple requests."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_duration_ms: float = 0.0
    total_tool_calls: int = 0
    errors_by_type: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    @property
    def avg_duration_ms(self) -> float:
        """Average request duration in milliseconds."""
        if self.total_requests == 0:
            return 0.0
        return self.total_duration_ms / self.total_requests

    @property
    def success_rate(self) -> float:
        """Success rate as a percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "success_rate": round(self.success_rate, 2),
            "total_tool_calls": self.total_tool_calls,
            "errors_by_type": dict(self.errors_by_type),
        }


class MetricsMiddleware(IMiddleware):
    """
    Middleware that collects request metrics.

    Tracks:
    - Request count and duration
    - Success/failure rates
    - Tool call counts
    - Error types
    """

    def __init__(
        self,
        max_history: int = 1000,
    ) -> None:
        """
        Initialize metrics middleware.

        Args:
            max_history: Maximum number of request metrics to keep.
        """
        self._max_history = max_history
        self._history: list[RequestMetrics] = []
        self._aggregate = AggregateMetrics()

    @property
    def name(self) -> str:
        """Return the middleware name."""
        return "metrics"

    @property
    def metrics(self) -> AggregateMetrics:
        """Get aggregate metrics."""
        return self._aggregate

    @property
    def history(self) -> list[RequestMetrics]:
        """Get recent request metrics."""
        return self._history.copy()

    async def process(
        self,
        context: "AgentContext",
        middleware_context: MiddlewareContext,
        next_handler: NextHandler,
    ) -> "ProviderResponse":
        """Collect metrics for the request."""
        start_time = time.time()
        request_metrics = RequestMetrics(
            task_id=context.task.id,
            request_id=context.request_id,
            start_time=start_time,
        )

        try:
            response = await next_handler(context)

            # Record success
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000

            request_metrics.end_time = end_time
            request_metrics.duration_ms = duration_ms
            request_metrics.status = "success"
            request_metrics.tool_calls = len(response.tool_calls) if response.tool_calls else 0

            self._aggregate.total_requests += 1
            self._aggregate.successful_requests += 1
            self._aggregate.total_duration_ms += duration_ms
            self._aggregate.total_tool_calls += request_metrics.tool_calls

            self._add_to_history(request_metrics)

            return response

        except Exception as e:
            # Record failure
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000

            request_metrics.end_time = end_time
            request_metrics.duration_ms = duration_ms
            request_metrics.status = "error"
            request_metrics.error = type(e).__name__

            self._aggregate.total_requests += 1
            self._aggregate.failed_requests += 1
            self._aggregate.total_duration_ms += duration_ms
            self._aggregate.errors_by_type[type(e).__name__] += 1

            self._add_to_history(request_metrics)

            raise

    def _add_to_history(self, metrics: RequestMetrics) -> None:
        """Add metrics to history, trimming if needed."""
        self._history.append(metrics)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def reset(self) -> None:
        """Reset all metrics."""
        self._history.clear()
        self._aggregate = AggregateMetrics()

    def get_summary(self) -> dict:
        """Get a summary of metrics."""
        return {
            "aggregate": self._aggregate.to_dict(),
            "recent_count": len(self._history),
        }
