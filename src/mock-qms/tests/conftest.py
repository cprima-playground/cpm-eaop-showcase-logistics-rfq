"""Offline test suite -- QMS_API_KEY set explicitly, stub masterdata client
(no network). Matches mock-rate/mock-tms/mock-fx's own conftest.py pattern."""

import pytest

import mock_qms.api as api_module
import mock_qms.auth as auth_module

TEST_API_KEY = "test-qms-key"

# matches systems/masterdata/fixtures/parties.jsonl
_KNOWN_PARTIES = {"ACME": "customer", "COSCO": "carrier", "MAERSK": "carrier"}


class StubMasterdataClient:
    def get(self, domain: str, code: str):
        if domain == "parties" and code in _KNOWN_PARTIES:
            return {"party_id": code, "kind": _KNOWN_PARTIES[code]}
        return None

    def list(self, domain: str):
        return []

    def exists(self, domain: str, code: str) -> bool:
        return self.get(domain, code) is not None


@pytest.fixture(autouse=True)
def _qms_api_key(monkeypatch):
    monkeypatch.setenv("QMS_API_KEY", TEST_API_KEY)
    auth_module._cached_key = None
    yield
    auth_module._cached_key = None


@pytest.fixture(autouse=True)
def _stub_masterdata(monkeypatch):
    monkeypatch.setattr(api_module, "_masterdata_client", lambda: StubMasterdataClient())
    yield
