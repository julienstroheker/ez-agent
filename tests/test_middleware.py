"""Tests for middleware."""

from __future__ import annotations

import pytest

from ez_agent.middleware.base import IMiddleware, MiddlewareChain, MiddlewareContext
from ez_agent.middleware.logging import LoggingMiddleware
from ez_agent.middleware.auth import AuthMiddleware, AuthenticationError
from ez_agent.middleware.metrics import MetricsMiddleware
from ez_agent.core.agent import AgentContext
from ez_agent.providers.base import ProviderResponse
from ez_agent.storage.base import TaskData


class TestMiddlewareChain:
    """Test middleware chain execution."""

    async def test_empty_chain_calls_handler(self):
        """Test that empty chain just calls final handler."""
        chain = MiddlewareChain()
        task = TaskData(id="test")
        context = AgentContext(task=task)

        async def handler(ctx):
            return ProviderResponse(content="Result")

        result = await chain.process(context, handler)
        assert result.content == "Result"

    async def test_middleware_order(self):
        """Test that middleware executes in order."""
        order = []

        class OrderMiddleware(IMiddleware):
            def __init__(self, name):
                self._name = name

            @property
            def name(self) -> str:
                return self._name

            async def process(self, ctx, mc, next_handler):
                order.append(f"{self._name}-before")
                result = await next_handler(ctx)
                order.append(f"{self._name}-after")
                return result

        chain = MiddlewareChain()
        chain.add(OrderMiddleware("first"))
        chain.add(OrderMiddleware("second"))

        task = TaskData(id="test")
        context = AgentContext(task=task)

        async def handler(ctx):
            order.append("handler")
            return ProviderResponse(content="Result")

        await chain.process(context, handler)

        assert order == [
            "first-before",
            "second-before",
            "handler",
            "second-after",
            "first-after",
        ]


class TestLoggingMiddleware:
    """Test logging middleware."""

    async def test_logs_request(self):
        """Test that requests are logged and processed."""
        middleware = LoggingMiddleware()
        task = TaskData(id="test-task")
        context = AgentContext(task=task)

        async def handler(ctx):
            return ProviderResponse(content="Response")

        result = await middleware.process(
            context,
            MiddlewareContext(),
            handler,
        )

        # Just verify the middleware doesn't break request processing
        assert result.content == "Response"


class TestAuthMiddleware:
    """Test authentication middleware."""

    @pytest.fixture
    def auth_middleware(self) -> AuthMiddleware:
        middleware = AuthMiddleware(enabled=True)
        middleware.add_token("valid-token")
        middleware.add_api_key("valid-api-key")
        return middleware

    async def test_disabled_auth_passes(self):
        """Test that disabled auth allows all requests."""
        middleware = AuthMiddleware(enabled=False)
        task = TaskData(id="test")
        context = AgentContext(task=task, metadata={})

        async def handler(ctx):
            return ProviderResponse(content="Result")

        result = await middleware.process(context, MiddlewareContext(), handler)
        assert result.content == "Result"

    async def test_valid_bearer_token(self, auth_middleware):
        """Test valid bearer token authentication."""
        task = TaskData(id="test")
        context = AgentContext(
            task=task,
            metadata={"auth_token": "valid-token", "auth_type": "bearer"},
        )

        async def handler(ctx):
            return ProviderResponse(content="Authenticated")

        result = await auth_middleware.process(
            context, MiddlewareContext(), handler
        )
        assert result.content == "Authenticated"

    async def test_invalid_token_raises(self, auth_middleware):
        """Test that invalid token raises error."""
        task = TaskData(id="test")
        context = AgentContext(
            task=task,
            metadata={"auth_token": "invalid-token", "auth_type": "bearer"},
        )

        async def handler(ctx):
            return ProviderResponse(content="Should not reach")

        with pytest.raises(AuthenticationError, match="Invalid bearer token"):
            await auth_middleware.process(context, MiddlewareContext(), handler)

    async def test_missing_auth_raises(self, auth_middleware):
        """Test that missing auth raises error."""
        task = TaskData(id="test")
        context = AgentContext(task=task, metadata={})

        async def handler(ctx):
            return ProviderResponse(content="Should not reach")

        with pytest.raises(AuthenticationError, match="Authentication required"):
            await auth_middleware.process(context, MiddlewareContext(), handler)

    async def test_allow_unauthenticated(self):
        """Test allowing unauthenticated requests."""
        middleware = AuthMiddleware(enabled=True, allow_unauthenticated=True)
        task = TaskData(id="test")
        context = AgentContext(task=task, metadata={})

        async def handler(ctx):
            return ProviderResponse(content="Result")

        result = await middleware.process(context, MiddlewareContext(), handler)
        assert result.content == "Result"

    def test_generate_token(self, auth_middleware):
        """Test token generation."""
        token = auth_middleware.generate_token()
        assert len(token) > 20
        assert token in auth_middleware._valid_tokens


class TestMetricsMiddleware:
    """Test metrics middleware."""

    async def test_tracks_successful_request(self):
        """Test that successful requests are tracked."""
        middleware = MetricsMiddleware()
        task = TaskData(id="test")
        context = AgentContext(task=task)

        async def handler(ctx):
            return ProviderResponse(content="Result")

        await middleware.process(context, MiddlewareContext(), handler)

        metrics = middleware.metrics
        assert metrics.total_requests == 1
        assert metrics.successful_requests == 1
        assert metrics.failed_requests == 0

    async def test_tracks_failed_request(self):
        """Test that failed requests are tracked."""
        middleware = MetricsMiddleware()
        task = TaskData(id="test")
        context = AgentContext(task=task)

        async def handler(ctx):
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await middleware.process(context, MiddlewareContext(), handler)

        metrics = middleware.metrics
        assert metrics.total_requests == 1
        assert metrics.failed_requests == 1
        assert "ValueError" in metrics.errors_by_type

    async def test_tracks_duration(self):
        """Test that request duration is tracked."""
        middleware = MetricsMiddleware()
        task = TaskData(id="test")
        context = AgentContext(task=task)

        async def handler(ctx):
            return ProviderResponse(content="Result")

        await middleware.process(context, MiddlewareContext(), handler)

        assert middleware.metrics.total_duration_ms > 0
        assert len(middleware.history) == 1
        assert middleware.history[0].duration_ms > 0

    def test_reset_metrics(self):
        """Test resetting metrics."""
        middleware = MetricsMiddleware()
        middleware._aggregate.total_requests = 100
        middleware.reset()

        assert middleware.metrics.total_requests == 0
        assert len(middleware.history) == 0
