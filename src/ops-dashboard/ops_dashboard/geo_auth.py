"""OIDC client_credentials token fetch for ops-dashboard's OWN machine
identity (workload.ops-dashboard, M10) -- the opposite direction from
sso.py's human Authorization Code login: this obtains a token for
ops-dashboard to authenticate ITSELF to a peer workload (geo-api's
GET /v1/legs/geometry), not to verify an inbound user's token. Cached
in-process, refreshed shortly before expiry -- never a network round-trip
per call once warm.

ops-dashboard never authenticated outbound to another OIDC-protected
workload before M10 (mock-* backends use a shared X-API-Key instead) --
this is a new pattern for this service, not a reuse of an existing one."""

from __future__ import annotations

import time

import httpx

from . import config


class TokenUnavailableError(RuntimeError):
    pass


class ServiceTokenProvider:
    def __init__(
        self, *, token_endpoint: str | None = None, client_id: str | None = None,
        client_secret: str | None = None, timeout: float = 5.0, verify=None,
    ):
        self._token_endpoint = token_endpoint or f"{config.keycloak_issuer_url()}/protocol/openid-connect/token"
        self._client_id = client_id or config.ops_dashboard_svc_client_id()
        self._client_secret = client_secret
        self._timeout = timeout
        self._verify = verify if verify is not None else config.caddy_ssl_context()
        self._token: str | None = None
        self._expires_at: float = 0.0

    def get_token(self) -> str:
        now = time.monotonic()
        if self._token and now < self._expires_at:
            return self._token

        secret = self._client_secret or config.ops_dashboard_svc_client_secret()
        try:
            r = httpx.post(
                self._token_endpoint,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": secret,
                },
                timeout=self._timeout,
                verify=self._verify,
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise TokenUnavailableError(
                f"client_credentials grant failed at {self._token_endpoint}: {exc}"
            ) from exc

        payload = r.json()
        self._token = payload["access_token"]
        # Refresh 30s before the token's real expiry -- a safety margin
        # against clock skew / request latency eating into whatever's left.
        expires_in = payload.get("expires_in", 60)
        self._expires_at = now + max(5, expires_in - 30)
        return self._token


_default_provider: ServiceTokenProvider | None = None


def default_token_provider() -> ServiceTokenProvider:
    global _default_provider
    if _default_provider is None:
        _default_provider = ServiceTokenProvider()
    return _default_provider
