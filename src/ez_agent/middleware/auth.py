"""Authentication middleware."""

from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING

from ez_agent.middleware.base import IMiddleware, MiddlewareContext, NextHandler
from ez_agent.providers.base import ProviderResponse

if TYPE_CHECKING:
    from ez_agent.core.agent import AgentContext


logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    def __init__(self, message: str, code: str = "unauthorized"):
        super().__init__(message)
        self.message = message
        self.code = code


class AuthMiddleware(IMiddleware):
    """
    Middleware that handles authentication.

    Supports:
    - Bearer token authentication
    - API key authentication

    Authentication info should be passed in context.metadata:
    - metadata["auth_token"]: Bearer token or API key
    - metadata["auth_type"]: "bearer" or "api_key"
    """

    def __init__(
        self,
        enabled: bool = True,
        valid_tokens: set[str] | None = None,
        valid_api_keys: set[str] | None = None,
        allow_unauthenticated: bool = False,
    ) -> None:
        """
        Initialize auth middleware.

        Args:
            enabled: Whether authentication is enabled.
            valid_tokens: Set of valid bearer tokens.
            valid_api_keys: Set of valid API keys.
            allow_unauthenticated: Allow requests without auth (for development).
        """
        self._enabled = enabled
        self._valid_tokens = valid_tokens or set()
        self._valid_api_keys = valid_api_keys or set()
        self._allow_unauthenticated = allow_unauthenticated

    @property
    def name(self) -> str:
        """Return the middleware name."""
        return "auth"

    def add_token(self, token: str) -> None:
        """Add a valid bearer token."""
        self._valid_tokens.add(token)

    def add_api_key(self, api_key: str) -> None:
        """Add a valid API key."""
        self._valid_api_keys.add(api_key)

    def generate_token(self) -> str:
        """Generate and register a new bearer token."""
        token = secrets.token_urlsafe(32)
        self._valid_tokens.add(token)
        return token

    def generate_api_key(self) -> str:
        """Generate and register a new API key."""
        api_key = f"eza_{secrets.token_urlsafe(32)}"
        self._valid_api_keys.add(api_key)
        return api_key

    async def process(
        self,
        context: "AgentContext",
        middleware_context: MiddlewareContext,
        next_handler: NextHandler,
    ) -> ProviderResponse:
        """Check authentication."""
        if not self._enabled:
            middleware_context.authenticated = True
            middleware_context.auth_method = "disabled"
            return await next_handler(context)

        # Get auth info from context metadata
        auth_token = context.metadata.get("auth_token")
        auth_type = context.metadata.get("auth_type", "bearer")

        if not auth_token:
            if self._allow_unauthenticated:
                logger.debug("Allowing unauthenticated request")
                middleware_context.authenticated = False
                return await next_handler(context)
            else:
                raise AuthenticationError(
                    "Authentication required",
                    code="missing_credentials",
                )

        # Validate based on auth type
        if auth_type == "bearer":
            if not self._validate_bearer_token(auth_token):
                raise AuthenticationError(
                    "Invalid bearer token",
                    code="invalid_token",
                )
            middleware_context.authenticated = True
            middleware_context.auth_method = "bearer"

        elif auth_type == "api_key":
            if not self._validate_api_key(auth_token):
                raise AuthenticationError(
                    "Invalid API key",
                    code="invalid_api_key",
                )
            middleware_context.authenticated = True
            middleware_context.auth_method = "api_key"

        else:
            raise AuthenticationError(
                f"Unsupported auth type: {auth_type}",
                code="unsupported_auth_type",
            )

        logger.debug(f"Authenticated via {auth_type}")
        return await next_handler(context)

    def _validate_bearer_token(self, token: str) -> bool:
        """Validate a bearer token."""
        # Constant-time comparison to prevent timing attacks
        for valid_token in self._valid_tokens:
            if secrets.compare_digest(token, valid_token):
                return True
        return False

    def _validate_api_key(self, api_key: str) -> bool:
        """Validate an API key."""
        for valid_key in self._valid_api_keys:
            if secrets.compare_digest(api_key, valid_key):
                return True
        return False
