"""Request-scoped audit context: correlation ID, request ID, verified principal.

The context is carried in contextvars so it works across FastAPI's sync
endpoints (which run in a threadpool - anyio copies the context into the
worker thread) and async code. A Starlette middleware (wired in main.py
during Stage 5) sets fresh IDs per request; the principal is attached only
AFTER server-side authentication - it is never trusted from the browser.
"""

from __future__ import annotations

import contextvars
import uuid

_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "mcp_correlation_id", default=""
)
_request_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "mcp_request_id", default=""
)
_principal: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "mcp_principal", default={}
)


def new_ids() -> tuple[str, str]:
    """Create a fresh (correlation_id, request_id) pair."""
    return uuid.uuid4().hex, uuid.uuid4().hex


def set_context(
    correlation_id: str,
    request_id: str,
    principal: dict | None = None,
) -> None:
    _correlation_id.set(correlation_id)
    _request_id.set(request_id)
    _principal.set(principal or {})


def reset_context() -> None:
    _correlation_id.set("")
    _request_id.set("")
    _principal.set({})


def get_correlation_id() -> str:
    return _correlation_id.get()


def get_request_id() -> str:
    return _request_id.get()


def get_principal() -> dict:
    return _principal.get()


def set_principal(principal: dict) -> None:
    """Attach the verified server-side principal (post-authentication)."""
    _principal.set(principal or {})


class AuditContextMiddleware:
    """Starlette middleware: fresh IDs per request + X-Correlation-ID echo.

    Wire it in main.py during Stage 5:

        from src.services.audit_context import AuditContextMiddleware
        app.add_middleware(AuditContextMiddleware)
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        headers = {
            k.decode().lower(): v.decode() for k, v in scope.get("headers", [])
        }
        correlation_id = headers.get("x-correlation-id") or uuid.uuid4().hex
        request_id = uuid.uuid4().hex
        set_context(correlation_id, request_id)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers_out = list(message.get("headers", []))
                headers_out.append((b"x-correlation-id", correlation_id.encode()))
                message = {**message, "headers": headers_out}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            reset_context()
