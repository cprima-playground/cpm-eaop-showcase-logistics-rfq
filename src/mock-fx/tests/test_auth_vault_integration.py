"""Proves mock-fx's auth resolves the API key from a LIVE Vault when FX_API_KEY
is unset -- the real fix for KNOWN-ISSUES.md #1. Skips (not fails) if Vault isn't
up, same discipline as the rfq_common/policy-evaluation live suites."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import mock_fx.auth as auth_module
from mock_fx.api import build_app
from rfq_common.secrets import VaultAdmin, VaultReader

VAULT_URL = "http://localhost:8200"
RFQ_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def vault_seeded_key(monkeypatch):
    if not VaultReader(VAULT_URL).health():
        pytest.skip(f"Vault not running on {VAULT_URL} (docker compose up -d in infra/vault/)")
    monkeypatch.delenv("FX_API_KEY", raising=False)  # force the Vault path
    auth_module._cached_key = None
    value = "vault-sourced-fx-key"
    VaultAdmin(VAULT_URL).put("rfq/fx-api-key", {"value": value})
    yield value
    auth_module._cached_key = None


def test_request_succeeds_with_vault_sourced_key(vault_seeded_key):
    client = TestClient(build_app())
    r = client.get("/exchange-rates/CNY/EUR", headers={"X-API-Key": vault_seeded_key})
    assert r.status_code == 200


def test_request_still_401s_with_wrong_key(vault_seeded_key):
    client = TestClient(build_app())
    r = client.get("/exchange-rates/CNY/EUR", headers={"X-API-Key": "wrong-key"})
    assert r.status_code == 401
