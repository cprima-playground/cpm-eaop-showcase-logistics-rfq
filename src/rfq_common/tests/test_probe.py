"""M8.3: rfq_common.probe -- semantics ported from ops-dashboard's
_check_service/_check_vault/_check_cedar/_check_identity_provider must
survive the extraction exactly (see probe.py's own module docstring for
why each of these specific cases matters -- not arbitrary test padding)."""

from __future__ import annotations

import httpx
import pytest

from rfq_common.probe import probe_cedar, probe_http_service, probe_oidc_issuer, probe_vault


class _FakeResponse:
    def __init__(self, status_code: int, json_body=None):
        self.status_code = status_code
        self._json_body = json_body

    def json(self):
        if self._json_body is None:
            raise ValueError("no json body")
        return self._json_body


def test_http_service_pass_on_200(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None: _FakeResponse(200))
    result = probe_http_service("tms-mcp", "http://tms-mcp:8104")
    assert result.status == "pass"
    assert result.reachable and result.authenticated


def test_http_service_fail_when_unreachable(monkeypatch):
    def _raise(url, timeout=None):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(httpx, "get", _raise)
    result = probe_http_service("mock-fx", "http://mock-fx:8001")
    assert result.status == "fail"
    assert not result.reachable


def test_vault_sealed_is_warn_not_fail(monkeypatch):
    """The semantic that must survive extraction: a sealed Vault answers
    (reachable) but every real secret read still fails (not pass)."""
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None: _FakeResponse(503, {"initialized": True, "sealed": True}))
    result = probe_vault("vault", "http://vault:8200")
    assert result.reachable is True
    assert result.status == "warn"


def test_vault_unsealed_and_initialized_is_pass(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None: _FakeResponse(200, {"initialized": True, "sealed": False}))
    result = probe_vault("vault", "http://vault:8200")
    assert result.status == "pass"


def test_cedar_reachable_but_zero_policies_is_warn_not_pass(monkeypatch):
    """The semantic that must survive extraction: a reachable-but-empty
    cedar-agent silently denies every future authorize() call -- not a
    real "up"."""
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None: _FakeResponse(200, []))
    result = probe_cedar("cedar-agent", "http://cedar-agent:8180")
    assert result.reachable is True
    assert result.status == "warn"


def test_cedar_with_policies_loaded_is_pass(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None: _FakeResponse(200, [{"id": "d1"}]))
    result = probe_cedar("cedar-agent", "http://cedar-agent:8180")
    assert result.status == "pass"


def test_oidc_issuer_mismatch_is_warn_not_pass(monkeypatch):
    """The semantic that must survive extraction: a Host-header-derived
    issuer mismatch breaks every real login silently -- this repo hit
    this for real (M7's live-stack stabilization pass)."""
    monkeypatch.setattr(
        httpx, "get",
        lambda url, timeout=None, verify=True: _FakeResponse(200, {"issuer": "http://keycloak:8080/realms/rfq"}),
    )
    result = probe_oidc_issuer("keycloak", "https://keycloak.eaop-logistics.localhost/realms/rfq")
    assert result.reachable is True
    assert result.status == "warn"


def test_oidc_issuer_match_is_pass(monkeypatch):
    monkeypatch.setattr(
        httpx, "get",
        lambda url, timeout=None, verify=True: _FakeResponse(200, {"issuer": "http://keycloak:8080/realms/rfq"}),
    )
    result = probe_oidc_issuer("keycloak", "http://keycloak:8080/realms/rfq")
    assert result.status == "pass"
