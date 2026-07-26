"""JWT/JWKS verification — IdP-agnostic (Keycloak dev, Entra test/prod; see
identity/claims-contract.md + deploy/environments.md). Mirrors cpm-eaop
src/spike/entra/verify.py's shape (PyJWKClient, issuer/audience/expiry
validation) but is not tied to any one IdP -- the caller supplies jwks_uri/issuer.

Split into an offline-verifiable core (`verify_with_jwks`, given a JWKS dict
directly -- what the tests use) and a thin online wrapper (`verify`, fetches JWKS
over HTTP) -- same split cpm-eaop uses between discovery+signing-key-fetch and the
actual decode/validate.
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass

import httpx
import jwt
from jwt import PyJWK, PyJWKClient

_jwks_clients: dict[str, PyJWKClient] = {}


class VerificationError(Exception):
    pass


@dataclass
class VerifiedToken:
    claims: dict
    issuer: str
    audience: str


def verify_with_jwks(token: str, jwks: dict, *, issuer: str, audience: str | None = None) -> VerifiedToken:
    """Verify signature/issuer/audience/expiry against an in-hand JWKS document
    (no network) -- what golden-fixture tests use."""
    if token.count(".") != 2:
        raise VerificationError("not a JWT (expected three dot-separated segments)")

    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")
    key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if key_data is None and len(jwks.get("keys", [])) == 1:
        key_data = jwks["keys"][0]  # single-key JWKS: kid mismatch tolerated (test fixtures)
    if key_data is None:
        raise VerificationError(f"no JWKS key found for kid={kid!r}")

    signing_key = PyJWK.from_dict(key_data)
    try:
        claims = jwt.decode(
            token, signing_key.key, algorithms=[signing_key.algorithm_name or "RS256"],
            audience=audience, issuer=issuer,
        )
    except jwt.PyJWTError as exc:
        raise VerificationError(str(exc)) from exc

    return VerifiedToken(claims=claims, issuer=claims["iss"], audience=str(claims.get("aud")))


def _jwks_client(jwks_uri: str) -> PyJWKClient:
    if jwks_uri not in _jwks_clients:
        _jwks_clients[jwks_uri] = PyJWKClient(jwks_uri, cache_keys=True)
    return _jwks_clients[jwks_uri]


def verify(token: str, *, jwks_uri: str, issuer: str, audience: str | None = None) -> VerifiedToken:
    """Verify against a live JWKS endpoint (Keycloak realm / Entra tenant)."""
    signing_key = _jwks_client(jwks_uri).get_signing_key_from_jwt(token)
    try:
        claims = jwt.decode(
            token, signing_key.key, algorithms=["RS256"], audience=audience, issuer=issuer,
        )
    except jwt.PyJWTError as exc:
        raise VerificationError(str(exc)) from exc
    return VerifiedToken(claims=claims, issuer=claims["iss"], audience=str(claims.get("aud")))


def fetch_jwks(jwks_uri: str, *, timeout: float = 10.0, verify: str | bool | None = None) -> dict:
    """`verify` overrides the TLS trust store for this one call -- a path to
    a CA bundle, or False to disable verification. Needed for an issuer whose
    cert chains to a local/internal CA (e.g. Caddy's, infra/caddy/) rather
    than a publicly-trusted one; None uses httpx's normal default (certifi)."""
    tls_verify = ssl.create_default_context(cafile=verify) if isinstance(verify, str) else (
        verify if verify is not None else True
    )
    r = httpx.get(jwks_uri, timeout=timeout, verify=tls_verify)
    r.raise_for_status()
    return r.json()
