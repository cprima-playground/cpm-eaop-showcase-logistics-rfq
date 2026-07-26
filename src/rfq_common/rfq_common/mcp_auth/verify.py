"""M6a + identity-unification pass: shared MCP-server-side authentication
adapter. Layer: this module sits BEFORE rfq_common.pep in the request path
-- it turns a raw Authorization header into VERIFIED claims, then hands
those (never an unverified dict) to rfq_common.pep.resolve_principal(). No
MCP handler may call resolve_principal() directly on request input;
authenticate_request() is the only sanctioned entry point.

Two verification mechanisms, both implementing `TokenVerifier`:
- `JwtTokenVerifier` (default) -- local JWKS signature verification via
  rfq_common.verify.verify(), which uses PyJWT's PyJWKClient(cache_keys=True)
  and therefore already refreshes on an unknown `kid` (key rotation handled
  for free, not reimplemented here). Issuer-agnostic: works against
  Keycloak or Entra once pointed at the right issuer/jwks_uri -- see
  tmp/oidc-identity-unification-plan.md.
- `IntrospectionTokenVerifier` -- the original RFC 7662 mechanism (matching
  spikes/mcp/authenticated-server/mcp_auth_spike/auth.py), KEPT, not
  deleted, as an opt-in for Keycloak-only deployments that specifically
  want live-revocation checking -- a real property JWKS-only verification
  doesn't give you. Each MCP server authenticates the introspection call
  with ITS OWN confidential client credentials, same as before.

`build_token_verifier()` is the ONE place that decides which to construct
-- no service re-implements this branch.

`expected_audience` stays optional (not made required): a real
client-credentials token minted from the live dev Keycloak realm during
this pass has `aud: "account"` (Keycloak's client_credentials default) --
no service's Keycloak client has an audience mapper configured. Making
this required now would break every live call immediately; real audience
enforcement needs Keycloak (and Entra) audience-mapper provisioning first,
which is a separate, explicitly out-of-scope follow-up here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import httpx

from rfq_common.oidc_discovery import discover_oidc_metadata


class AuthenticationError(Exception):
    pass


def extract_bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("missing or malformed Authorization header")
    token = authorization[len("Bearer "):].strip()
    if not token:
        raise AuthenticationError("empty bearer token")
    return token


class TokenVerifier(Protocol):
    def verify(self, token: str, *, expected_audience: str | None = None) -> dict:
        """Returns verified claims on an active/valid token. Raises
        AuthenticationError otherwise."""
        ...


class JwtTokenVerifier:
    """Local JWKS signature verification -- issuer-agnostic. Wraps
    rfq_common.verify.verify(), NOT the offline fetch_jwks()+
    verify_with_jwks() pair (that combo has no key-rotation refresh)."""

    def __init__(self, *, issuer: str, jwks_uri: str, timeout: float = 5.0):
        self._issuer = issuer
        self._jwks_uri = jwks_uri
        self._timeout = timeout

    def verify(self, token: str, *, expected_audience: str | None = None) -> dict:
        from rfq_common.verify import VerificationError, verify as verify_jwks

        try:
            return verify_jwks(
                token, jwks_uri=self._jwks_uri, issuer=self._issuer, audience=expected_audience,
            ).claims
        except VerificationError as exc:
            raise AuthenticationError(str(exc)) from exc


class IntrospectionTokenVerifier:
    """RFC 7662 token introspection against Keycloak -- the original
    mechanism, kept as an opt-in (see module docstring)."""

    def __init__(self, *, introspection_endpoint: str, client_id: str, client_secret: str, timeout: float = 5.0):
        self._introspection_endpoint = introspection_endpoint
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout = timeout

    def verify(self, token: str, *, expected_audience: str | None = None) -> dict:
        try:
            response = httpx.post(
                self._introspection_endpoint,
                data={"token": token},
                auth=(self._client_id, self._client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self._timeout,
            )
            response.raise_for_status()
            claims: dict = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AuthenticationError(f"token introspection failed: {exc}") from exc

        if not claims.get("active", False):
            raise AuthenticationError("token is not active")

        if expected_audience is not None:
            audience = claims.get("aud")
            allowed = audience == expected_audience or (isinstance(audience, list) and expected_audience in audience)
            if not allowed:
                raise AuthenticationError(f"token audience {audience!r} does not include {expected_audience!r}")

        return claims


def build_token_verifier(
    *,
    mode: str,
    oidc_issuer_url: str,
    introspection_endpoint: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> TokenVerifier:
    """The ONE place that decides jwks-vs-introspection and constructs the
    right object -- discovery happens here (explicit, separate step)
    before construction; the verifier classes themselves never discover
    anything, they're dumb wrappers over an already-resolved
    issuer/jwks_uri or introspection_endpoint."""
    if mode == "introspection":
        if introspection_endpoint is None or client_id is None or client_secret is None:
            raise ValueError("introspection mode requires introspection_endpoint, client_id, client_secret")
        return IntrospectionTokenVerifier(
            introspection_endpoint=introspection_endpoint, client_id=client_id, client_secret=client_secret,
        )
    if mode != "jwks":
        raise ValueError(f"unknown verification mode {mode!r} (expected 'jwks' or 'introspection')")
    metadata = discover_oidc_metadata(oidc_issuer_url)
    return JwtTokenVerifier(issuer=metadata.issuer, jwks_uri=metadata.jwks_uri)


def authenticate_request(
    authorization: str | None,
    *,
    verifier: TokenVerifier,
    expected_audience: str | None = None,
    root: Path | None = None,
):
    """extract_bearer_token -> verifier.verify -> resolve_principal, in
    that order -- the only sanctioned way an MCP handler turns request
    input into a ResolvedPrincipal. Never pass unverified claims (or the
    raw header) directly to resolve_principal()."""
    from rfq_common.pep import resolve_principal

    token = extract_bearer_token(authorization)
    claims = verifier.verify(token, expected_audience=expected_audience)
    return resolve_principal(claims, root=root)
