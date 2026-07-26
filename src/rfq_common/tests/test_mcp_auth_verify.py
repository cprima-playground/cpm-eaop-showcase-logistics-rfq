"""rfq_common.mcp_auth.verify -- TokenVerifier protocol + build_token_verifier()
factory. See tmp/oidc-identity-unification-plan.md for the design: one
shared factory, not each of the 7 services re-implementing the jwks-vs-
introspection branch."""

import httpx
import pytest

from rfq_common.mcp_auth import (
    AuthenticationError,
    IntrospectionTokenVerifier,
    JwtTokenVerifier,
    build_token_verifier,
    extract_bearer_token,
)


def test_extract_bearer_token_requires_bearer_prefix():
    with pytest.raises(AuthenticationError):
        extract_bearer_token("Basic abc")
    with pytest.raises(AuthenticationError):
        extract_bearer_token(None)
    assert extract_bearer_token("Bearer xyz") == "xyz"


def test_build_token_verifier_jwks_mode(monkeypatch):
    def fake_get(url, timeout=None):
        return httpx.Response(200, json={
            "issuer": "https://mcp-auth-issuer.example.test",
            "jwks_uri": "https://mcp-auth-issuer.example.test/keys",
            "token_endpoint": "https://mcp-auth-issuer.example.test/token",
        }, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    verifier = build_token_verifier(mode="jwks", oidc_issuer_url="https://mcp-auth-issuer.example.test")
    assert isinstance(verifier, JwtTokenVerifier)


def test_build_token_verifier_introspection_mode():
    verifier = build_token_verifier(
        mode="introspection", oidc_issuer_url="https://mcp-auth-issuer.example.test",
        introspection_endpoint="https://mcp-auth-issuer.example.test/introspect",
        client_id="svc", client_secret="secret",
    )
    assert isinstance(verifier, IntrospectionTokenVerifier)


def test_build_token_verifier_introspection_mode_requires_credentials():
    with pytest.raises(ValueError):
        build_token_verifier(mode="introspection", oidc_issuer_url="https://mcp-auth-issuer.example.test")


def test_build_token_verifier_rejects_unknown_mode():
    with pytest.raises(ValueError):
        build_token_verifier(mode="carrier-pigeon", oidc_issuer_url="https://mcp-auth-issuer.example.test")


def test_introspection_token_verifier_rejects_inactive_token(monkeypatch):
    def fake_post(url, *, data, auth, headers, timeout):
        return httpx.Response(200, json={"active": False}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    verifier = IntrospectionTokenVerifier(
        introspection_endpoint="https://mcp-auth-issuer.example.test/introspect",
        client_id="svc", client_secret="secret",
    )
    with pytest.raises(AuthenticationError):
        verifier.verify("some-token")


def test_introspection_token_verifier_enforces_audience_when_given(monkeypatch):
    def fake_post(url, *, data, auth, headers, timeout):
        return httpx.Response(200, json={"active": True, "aud": "someone-else"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    verifier = IntrospectionTokenVerifier(
        introspection_endpoint="https://mcp-auth-issuer.example.test/introspect",
        client_id="svc", client_secret="secret",
    )
    with pytest.raises(AuthenticationError):
        verifier.verify("some-token", expected_audience="tms-mcp-svc")


def test_introspection_token_verifier_skips_audience_check_when_none(monkeypatch):
    """expected_audience=None means skip the check -- deliberate, not a
    forced-required param, per this pass's real-token finding that no
    Keycloak client here has an audience mapper configured
    (tmp/oidc-identity-unification-plan.md)."""
    def fake_post(url, *, data, auth, headers, timeout):
        return httpx.Response(200, json={"active": True, "aud": "account"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    verifier = IntrospectionTokenVerifier(
        introspection_endpoint="https://mcp-auth-issuer.example.test/introspect",
        client_id="svc", client_secret="secret",
    )
    claims = verifier.verify("some-token")
    assert claims["active"] is True
