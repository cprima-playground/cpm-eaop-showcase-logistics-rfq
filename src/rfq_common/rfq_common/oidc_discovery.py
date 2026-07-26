"""OIDC discovery -- both Keycloak and Entra publish a standard
`.well-known/openid-configuration` document; using it removes the need for
any provider-specific URL-shape knowledge (Keycloak's `/realms/{realm}/...`
vs Entra's `/v2.0/...`/`/discovery/v2.0/...`) from settings/config code.

Caching is per-issuer, process-lifetime: the *document* (which URL is the
JWKS endpoint) is stable -- provider-side changes to it are rare and
operationally announced, not silent. `refresh_oidc_metadata()` is the
manual escape hatch for that rare case, not a TTL. The *keys themselves*
are what actually rotates routinely, and that's handled separately,
automatically, by rfq_common.verify's PyJWKClient(cache_keys=True) --
this module never touches key material, only endpoint URLs.
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel


class OidcMetadata(BaseModel):
    issuer: str
    jwks_uri: str
    token_endpoint: str
    authorization_endpoint: str | None = None


_metadata_cache: dict[str, OidcMetadata] = {}


def discover_oidc_metadata(issuer: str, *, timeout: float = 5.0) -> OidcMetadata:
    """GET {issuer}/.well-known/openid-configuration. Cached per-issuer for
    the process lifetime -- call refresh_oidc_metadata(issuer) first if you
    need to force a re-fetch (provider-side endpoint change)."""
    if issuer in _metadata_cache:
        return _metadata_cache[issuer]

    r = httpx.get(f"{issuer.rstrip('/')}/.well-known/openid-configuration", timeout=timeout)
    r.raise_for_status()
    doc = r.json()
    metadata = OidcMetadata(
        issuer=doc.get("issuer", issuer),
        jwks_uri=doc["jwks_uri"],
        token_endpoint=doc["token_endpoint"],
        authorization_endpoint=doc.get("authorization_endpoint"),
    )
    _metadata_cache[issuer] = metadata
    return metadata


def refresh_oidc_metadata(issuer: str) -> None:
    """Clears the one cache entry for `issuer` -- next discover_oidc_metadata()
    call re-fetches. Manual, not automatic (see module docstring)."""
    _metadata_cache.pop(issuer, None)
