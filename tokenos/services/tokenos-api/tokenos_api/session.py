"""Per-visitor scoping for the hosted demonstration.

The application is single-tenant by design, and its tenant identity comes from
server configuration rather than anything a browser sends. That is the right
default and is not changed here.

A public demonstration has a different problem: several judges share one
instance, and one visitor's run history should not appear in another's. This
issues an opaque, server-generated session identifier in a cookie and exposes it
through a context variable so request handlers can scope what they return.

Two deliberate limits:

- It is active only in simulated mode. Local and Foundry deployments keep their
  existing single-tenant behaviour exactly.
- It scopes what a visitor is *shown*, not what the server stores. Runs remain
  in one store and reporting still aggregates across all of them. This is a
  demonstration convenience, not a security boundary, and the README says so.
"""

from __future__ import annotations

import secrets
from contextvars import ContextVar

from .config import settings

COOKIE_NAME = "tokenos_session"

# 32 bytes of entropy. Guessing another visitor's identifier is not a
# realistic attack; reading it from their browser is out of scope for a
# same-site demonstration cookie.
_TOKEN_BYTES = 32

_session: ContextVar[str] = ContextVar("tokenos_session", default="")


def current_session() -> str:
    """Identifier for the visitor making this request, or '' outside a request."""
    return _session.get()


def new_session_id() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def _is_wellformed(value: str) -> bool:
    """Accepts only the shape this module issues.

    A crafted cookie must never become a storage key, so anything that is not
    plain URL-safe base64 of a sane length is discarded and replaced.
    """
    if not value or len(value) > 128 or not value.isascii():
        return False
    return value.replace("-", "").replace("_", "").isalnum()


class SessionScopeMiddleware:
    """Issues and carries a per-visitor identifier in simulated mode only.

    Written as raw ASGI rather than Starlette's BaseHTTPMiddleware on purpose.
    BaseHTTPMiddleware runs the downstream application in a separate task, and
    a ContextVar set in its dispatch does not reliably reach the endpoint, so
    request handlers saw an empty session and every visitor's history filtered
    to nothing. Plain ASGI keeps one context for the whole request.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not settings.simulated:
            await self.app(scope, receive, send)
            return

        cookies = _parse_cookies(scope)
        existing = cookies.get(COOKIE_NAME, "")
        session_id = existing if _is_wellformed(existing) else new_session_id()
        issue = session_id != existing

        async def send_with_cookie(message):
            if issue and message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                cookie = (
                    f"{COOKIE_NAME}={session_id}; Path=/; Max-Age={60 * 60 * 8}; "
                    "HttpOnly; Secure; SameSite=Lax"
                )
                headers.append((b"set-cookie", cookie.encode("latin-1")))
            await send(message)

        token = _session.set(session_id)
        try:
            await self.app(scope, receive, send_with_cookie)
        finally:
            _session.reset(token)


def _parse_cookies(scope) -> dict[str, str]:
    raw = b""
    for name, value in scope.get("headers", []):
        if name == b"cookie":
            raw = value
            break
    if not raw:
        return {}
    cookies: dict[str, str] = {}
    for part in raw.decode("latin-1").split(";"):
        if "=" in part:
            key, _, value = part.partition("=")
            cookies[key.strip()] = value.strip()
    return cookies
