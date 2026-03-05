"""Bearer token authentication middleware for FastAPI."""

from __future__ import annotations

import structlog
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

log = structlog.get_logger()

# Paths that don't require authentication
_PUBLIC_PATHS = frozenset({
    "/docs",
    "/openapi.json",
    "/redoc",
    "/static",
    "/ws/chat",  # WebSocket has its own auth story
})


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that requires Bearer token authentication.

    Checks the ``Authorization: Bearer <token>`` header against the
    expected token.  Public paths (docs, static) are exempt.

    Parameters
    ----------
    app:
        The FastAPI application.
    token:
        The expected Bearer token.
    """

    def __init__(self, app: object, token: str) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._token = token

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Allow public paths
        path = request.url.path
        if any(path.startswith(p) for p in _PUBLIC_PATHS):
            return await call_next(request)

        # Allow health check
        if path == "/status" and request.method == "GET":
            return await call_next(request)

        # Check Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail="Missing or invalid Authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = auth_header[7:]  # Strip "Bearer "
        if token != self._token:
            raise HTTPException(
                status_code=403,
                detail="Invalid token",
            )

        return await call_next(request)
