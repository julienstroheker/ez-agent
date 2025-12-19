"""Base middleware interface and chain executor."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ez_agent.core.agent import AgentContext
    from ez_agent.providers.base import ProviderResponse


# Type alias for the next handler in the chain
NextHandler = Callable[["AgentContext"], Awaitable["ProviderResponse"]]


@dataclass
class MiddlewareContext:
    """
    Additional context passed through middleware.

    Allows middleware to communicate with each other and add metadata.
    """

    metadata: dict[str, Any] = field(default_factory=dict)
    start_time: float | None = None
    request_id: str | None = None
    user_id: str | None = None
    authenticated: bool = False
    auth_method: str | None = None

    def set(self, key: str, value: Any) -> None:
        """Set a metadata value."""
        self.metadata[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get a metadata value."""
        return self.metadata.get(key, default)


class IMiddleware(ABC):
    """
    Abstract interface for middleware.

    Middleware can:
    - Modify the context before processing
    - Modify the response after processing
    - Short-circuit the chain by not calling next
    - Add logging, metrics, auth, etc.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the middleware name."""
        ...

    @abstractmethod
    async def process(
        self,
        context: "AgentContext",
        middleware_context: MiddlewareContext,
        next_handler: NextHandler,
    ) -> "ProviderResponse":
        """
        Process the request.

        Args:
            context: Agent context with task and messages.
            middleware_context: Shared middleware context.
            next_handler: Next middleware or final handler.

        Returns:
            Provider response (from next handler or short-circuited).
        """
        ...


class MiddlewareChain:
    """
    Chain of middleware that processes requests in order.

    Middleware is executed in the order added, with the final handler
    called last. Each middleware can modify the context, call the next
    handler, and modify the response.
    """

    def __init__(self) -> None:
        """Initialize an empty chain."""
        self._middleware: list[IMiddleware] = []

    def add(self, middleware: IMiddleware) -> "MiddlewareChain":
        """
        Add middleware to the chain.

        Args:
            middleware: Middleware to add.

        Returns:
            Self for chaining.
        """
        self._middleware.append(middleware)
        return self

    def add_many(self, *middleware: IMiddleware) -> "MiddlewareChain":
        """
        Add multiple middleware to the chain.

        Args:
            *middleware: Middleware instances to add.

        Returns:
            Self for chaining.
        """
        for m in middleware:
            self._middleware.append(m)
        return self

    async def process(
        self,
        context: "AgentContext",
        final_handler: NextHandler,
    ) -> "ProviderResponse":
        """
        Process a request through the middleware chain.

        Args:
            context: Agent context.
            final_handler: Final handler to call after all middleware.

        Returns:
            Provider response.
        """
        middleware_context = MiddlewareContext(
            request_id=context.request_id,
        )

        # Build the chain from the end
        handler = final_handler

        for middleware in reversed(self._middleware):
            # Capture the current handler and middleware in the closure
            current_handler = handler
            current_middleware = middleware

            async def make_handler(
                ctx: "AgentContext",
                h: NextHandler = current_handler,
                m: IMiddleware = current_middleware,
                mc: MiddlewareContext = middleware_context,
            ) -> "ProviderResponse":
                return await m.process(ctx, mc, h)

            handler = make_handler

        return await handler(context)

    def __len__(self) -> int:
        """Return the number of middleware in the chain."""
        return len(self._middleware)

    def __iter__(self):
        """Iterate over middleware."""
        return iter(self._middleware)
