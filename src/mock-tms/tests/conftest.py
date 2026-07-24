"""Offline test suite -- TMS_API_KEY set explicitly, stub masterdata client
(same real location codes, no network). The separate skip-gated
test_masterdata_integration.py proves the real call."""

import pytest

import mock_tms.api as api_module
import mock_tms.auth as auth_module

TEST_API_KEY = "test-tms-key"

# real UN/LOCODE codes referenced by systems/tms/fixtures/routes.yaml
_KNOWN_LOCATIONS = {
    "CNSHA", "CNNGB", "CNPVG", "SGSIN", "DEHAM", "NLRTM", "BEANR", "PLGDN",
    "GRPIR", "ITGOA", "DEDUI", "DENUE", "CZPRG", "DEFRA", "DEMUC",
    "USLAX", "USOAK", "AEJEA", "ZADUR", "ITMIL",
}


class StubMasterdataClient:
    def get(self, domain: str, code: str):
        if domain == "locations" and code in _KNOWN_LOCATIONS:
            return {"locode": code}
        return None

    def list(self, domain: str):
        return []

    def exists(self, domain: str, code: str) -> bool:
        return self.get(domain, code) is not None


@pytest.fixture(autouse=True)
def _tms_api_key(monkeypatch):
    monkeypatch.setenv("TMS_API_KEY", TEST_API_KEY)
    auth_module._cached_key = None
    yield
    auth_module._cached_key = None


@pytest.fixture(autouse=True)
def _stub_masterdata(monkeypatch):
    monkeypatch.setattr(api_module, "_masterdata_client", lambda: StubMasterdataClient())
    yield
