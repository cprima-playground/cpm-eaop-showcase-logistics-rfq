"""Keycloak/OAuth token introspection for the authenticated MCP spike.

This is intentionally an RFC 7662 resource-server adapter. It makes an
identity-server request for each MCP request so the spike exposes the complete
authentication path. Cedar authorization is deliberately not part of this
first slice.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from mcp.server.auth.provider import AccessToken, TokenVerifier

from .config import Settings

logger = logging.getLogger(__name__)


class IntrospectionTokenVerifier(TokenVerifier):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            verify=settings.ca_cert or True,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def verify_token(self, token: str) -> AccessToken | None:
        auth = None
        if self.settings.introspection_client_id and self.settings.introspection_client_secret:
            auth = httpx.BasicAuth(
                self.settings.introspection_client_id,
                self.settings.introspection_client_secret,
            )

        try:
            response = await self._client.post(
                str(self.settings.introspection_endpoint),
                data={"token": token},
                auth=auth,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            claims: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("MCP token introspection failed: %s", exc)
            return None

        if not claims.get("active", False):
            return None
        if not self._audience_allowed(claims.get("aud")):
            logger.warning("MCP token audience rejected")
            return None

        scopes = claims.get("scope", "")
        if isinstance(scopes, str):
            scopes = scopes.split()
        if self.settings.required_scope and self.settings.required_scope not in scopes:
            logger.warning("MCP token missing required scope")
            return None

        return AccessToken(
            token=token,
            client_id=str(claims.get("client_id", claims.get("azp", "unknown"))),
            scopes=list(scopes),
            expires_at=claims.get("exp"),
            resource=str(self.settings.public_url),
            subject=claims.get("sub"),
            claims=claims,
        )

    def _audience_allowed(self, audience: Any) -> bool:
        expected = self.settings.expected_audience
        if not expected:
            return True
        if isinstance(audience, list):
            return expected in audience
        return audience == expected
