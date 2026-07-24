"""Keeps the offline test suite Vault-independent: FX_API_KEY is set explicitly
per test, and auth's module-level credential cache is reset so tests don't leak
into each other (mirrors the two-tier discipline: unit tests never touch Vault;
test_auth_vault_integration.py is the separate skip-gated live suite)."""

import pytest

import mock_fx.auth as auth_module

TEST_API_KEY = "test-fx-key"


@pytest.fixture(autouse=True)
def _fx_api_key(monkeypatch):
    monkeypatch.setenv("FX_API_KEY", TEST_API_KEY)
    auth_module._cached_key = None
    yield
    auth_module._cached_key = None
