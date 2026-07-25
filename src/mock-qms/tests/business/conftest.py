"""Live cross-service business-scenario tests -- no autouse stubbing here
(that's unit/conftest.py's job, deliberately not inherited by this
directory). These tests hit real running qms/tms/rate/fx/masterdata
services; skip (not fail) if any required service isn't up."""

from pathlib import Path

import httpx
import pytest

from rfq_common.secrets import SecretsClient

RFQ_ROOT = Path(__file__).resolve().parents[4]
INVENTORY_PATH = RFQ_ROOT / "identity" / "credentials-inventory.yaml"

QMS_URL = "http://127.0.0.1:8007"
TMS_URL = "http://127.0.0.1:8004"


def service_up(url: str, *, timeout: float = 1.0) -> bool:
    # Deliberately not imported from integration/conftest.py -- sibling
    # conftest.py modules across unit/integration/business all share the
    # bare module name "conftest" with no __init__.py package structure,
    # so a plain `from conftest import X` resolves to whichever "conftest"
    # Python's import system already has in sys.modules (often itself,
    # mid-init) rather than the other directory's file. Small enough to
    # duplicate rather than fight that.
    try:
        return httpx.get(url, timeout=timeout).status_code == 200
    except Exception:
        return False


def _api_key(name: str) -> str | None:
    try:
        return SecretsClient("dev", inventory_path=INVENTORY_PATH).get(name)
    except Exception:
        return None


@pytest.fixture(scope="module")
def qms_client():
    if not service_up(f"{QMS_URL}/healthz"):
        pytest.skip(f"mock-qms not running on {QMS_URL}")
    key = _api_key("qms-api-key")
    if key is None:
        pytest.skip("Vault not running or qms-api-key not seeded")
    client = httpx.Client(base_url=QMS_URL, headers={"X-API-Key": key}, timeout=10.0)
    yield client
    client.close()


@pytest.fixture(scope="module")
def tms_client():
    if not service_up(f"{TMS_URL}/healthz"):
        pytest.skip(f"mock-tms not running on {TMS_URL}")
    key = _api_key("tms-api-key")
    if key is None:
        pytest.skip("Vault not running or tms-api-key not seeded")
    client = httpx.Client(base_url=TMS_URL, headers={"X-API-Key": key}, timeout=10.0)
    yield client
    client.close()
