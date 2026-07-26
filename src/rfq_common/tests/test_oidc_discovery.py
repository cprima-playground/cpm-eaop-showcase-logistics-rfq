"""OIDC discovery -- issuer-agnostic (Keycloak and Entra both publish
.well-known/openid-configuration). Caching is per-issuer, process-lifetime,
with a manual refresh escape hatch -- see rfq_common.oidc_discovery's
module docstring for why (the endpoint URLs are stable; the signing keys,
which actually rotate, are handled separately by rfq_common.verify's
PyJWKClient)."""

import httpx
import pytest

from rfq_common.oidc_discovery import discover_oidc_metadata, refresh_oidc_metadata


@pytest.fixture(autouse=True)
def _clear_cache():
    yield
    refresh_oidc_metadata("https://issuer.example.test")
    refresh_oidc_metadata("https://issuer.example.test/other")


def test_discover_oidc_metadata_parses_well_known_document(monkeypatch):
    def fake_get(url, timeout=None):
        assert url == "https://issuer.example.test/.well-known/openid-configuration"
        return httpx.Response(200, json={
            "issuer": "https://issuer.example.test",
            "jwks_uri": "https://issuer.example.test/keys",
            "token_endpoint": "https://issuer.example.test/token",
            "authorization_endpoint": "https://issuer.example.test/authorize",
        }, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    metadata = discover_oidc_metadata("https://issuer.example.test")
    assert metadata.jwks_uri == "https://issuer.example.test/keys"
    assert metadata.token_endpoint == "https://issuer.example.test/token"
    assert metadata.authorization_endpoint == "https://issuer.example.test/authorize"


def test_discover_oidc_metadata_is_cached_per_issuer(monkeypatch):
    calls = []

    def fake_get(url, timeout=None):
        calls.append(url)
        return httpx.Response(200, json={
            "issuer": "https://issuer.example.test/other",
            "jwks_uri": "https://issuer.example.test/other/keys",
            "token_endpoint": "https://issuer.example.test/other/token",
        }, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    discover_oidc_metadata("https://issuer.example.test/other")
    discover_oidc_metadata("https://issuer.example.test/other")
    assert len(calls) == 1  # second call served from cache, no second GET


def test_refresh_oidc_metadata_forces_a_re_fetch(monkeypatch):
    calls = []

    def fake_get(url, timeout=None):
        calls.append(url)
        return httpx.Response(200, json={
            "issuer": "https://issuer.example.test",
            "jwks_uri": "https://issuer.example.test/keys",
            "token_endpoint": "https://issuer.example.test/token",
        }, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    discover_oidc_metadata("https://issuer.example.test")
    refresh_oidc_metadata("https://issuer.example.test")
    discover_oidc_metadata("https://issuer.example.test")
    assert len(calls) == 2
