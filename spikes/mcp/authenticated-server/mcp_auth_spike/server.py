from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import uvicorn
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import Context, FastMCP
from pydantic import AnyHttpUrl
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .auth import IntrospectionTokenVerifier
from .config import Settings


class CorrelationIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = next(
            (value.decode("latin-1") for key, value in scope.get("headers", []) if key.lower() == b"x-correlation-id"),
            None,
        )
        correlation_id = incoming if incoming and len(incoming) <= 128 else str(uuid.uuid4())
        scope.setdefault("state", {})["correlation_id"] = correlation_id

        async def send_with_correlation(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-correlation-id", correlation_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_correlation)


class InspectorCorsMiddleware:
    """Development-only CORS wrapper for the browser-based MCP Inspector."""

    def __init__(self, app: ASGIApp, allowed_origins: set[str]) -> None:
        self.app = app
        self.allowed_origins = allowed_origins

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_headers = {key.decode().lower(): value.decode() for key, value in scope.get("headers", [])}
        origin = request_headers.get("origin")
        if not origin or origin not in self.allowed_origins:
            await self.app(scope, receive, send)
            return

        cors_headers = [
            (b"access-control-allow-origin", origin.encode("latin-1")),
            (b"access-control-allow-credentials", b"true"),
            (b"access-control-expose-headers", b"MCP-Session-Id, X-Correlation-Id, WWW-Authenticate"),
            (b"vary", b"Origin"),
        ]

        if scope.get("method") == "OPTIONS":
            requested_headers = request_headers.get("access-control-request-headers", "")
            preflight_headers = cors_headers + [
                (b"access-control-allow-methods", b"GET, POST, DELETE, OPTIONS"),
                (b"access-control-allow-headers", requested_headers.encode("latin-1") or b"*"),
                (b"access-control-max-age", b"600"),
            ]
            await send({"type": "http.response.start", "status": 204, "headers": preflight_headers})
            await send({"type": "http.response.body", "body": b""})
            return

        async def send_with_cors(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing_headers = list(message.get("headers", []))
                already_has_cors = any(key.lower() == b"access-control-allow-origin" for key, _ in existing_headers)
                if not already_has_cors:
                    message = {**message, "headers": existing_headers + cors_headers}
            await send(message)

        await self.app(scope, receive, send_with_cors)


def create_server(settings: Settings | None = None) -> tuple[FastMCP, IntrospectionTokenVerifier]:
    settings = settings or Settings()
    verifier = IntrospectionTokenVerifier(settings)
    required_scopes = [settings.required_scope] if settings.required_scope else []

    mcp = FastMCP(
        name="RFQ Authenticated MCP Spike",
        instructions="Authenticated MCP server used to validate the local OAuth transport contract.",
        host=settings.host,
        port=settings.port,
        token_verifier=verifier,
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(str(settings.issuer_url)),
            resource_server_url=AnyHttpUrl(str(settings.public_url)),
            required_scopes=required_scopes,
        ),
        json_response=True,
    )

    @mcp.tool()
    async def echo_authenticated(message: str, ctx: Context) -> dict[str, Any]:
        """Return a message and the authenticated caller identity metadata."""
        access_token = get_access_token()
        return {
            "message": message,
            "authenticated": True,
            "client_id": access_token.client_id if access_token else None,
            "correlation_id": ctx.request_id,
        }

    @mcp.resource("demo://authenticated-contract")
    async def authenticated_contract() -> str:
        """Describe the non-MCP headers expected by this spike."""
        return json.dumps(
            {
                "required": ["Authorization", "Accept", "Content-Type"],
                "after_initialize": ["MCP-Protocol-Version"],
                "propagated": ["X-Correlation-Id", "traceparent"],
                "authorization": "OAuth 2.0 bearer token validated by Keycloak introspection",
                "policy": "not implemented in this first spike",
            },
            indent=2,
        )

    return mcp, verifier


def main() -> None:
    settings = Settings()
    logging.basicConfig(level=settings.log_level)
    mcp, verifier = create_server(settings)
    mcp_app = mcp.streamable_http_app()
    allowed_origins = {origin.strip() for origin in settings.allowed_origins.split(",") if origin.strip()}
    app = InspectorCorsMiddleware(mcp_app, allowed_origins)
    app = CorrelationIdMiddleware(app)
    try:
        uvicorn.run(app, host=settings.host, port=settings.port, log_level=settings.log_level.lower())
    finally:
        import asyncio

        asyncio.run(verifier.close())
