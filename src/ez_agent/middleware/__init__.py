"""Middleware system for the agent."""

from ez_agent.middleware.base import IMiddleware, MiddlewareChain, MiddlewareContext
from ez_agent.middleware.logging import LoggingMiddleware
from ez_agent.middleware.auth import AuthMiddleware
from ez_agent.middleware.metrics import MetricsMiddleware

__all__ = [
    "IMiddleware",
    "MiddlewareChain",
    "MiddlewareContext",
    "LoggingMiddleware",
    "AuthMiddleware",
    "MetricsMiddleware",
]
