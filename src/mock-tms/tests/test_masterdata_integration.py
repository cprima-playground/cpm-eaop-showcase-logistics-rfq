"""Proves TMS genuinely consumes masterdata via its REST API (ADR-010). Skips
(not fails) if masterdata isn't running."""

from pathlib import Path

import httpx
import pytest

from mock_tms.store import TmsStore, UnknownLocationError
from rfq_common.masterdata_client import MasterdataClient, MasterdataUnavailableError

MASTERDATA_URL = "http://localhost:8003"
RFQ_ROOT = Path(__file__).resolve().parents[3]
TMS_FIXTURES_DIR = RFQ_ROOT / "systems" / "tms" / "fixtures"


def _masterdata_up() -> bool:
    try:
        return httpx.get(f"{MASTERDATA_URL}/healthz", timeout=1.0).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def masterdata_key():
    if not _masterdata_up():
        pytest.skip(f"masterdata not running on {MASTERDATA_URL}")
    key = httpx.get(
        "http://localhost:8200/v1/secret/data/rfq/masterdata-api-key",
        headers={"X-Vault-Token": "rfq-dev-root"}, timeout=5.0,
    )
    if key.status_code != 200:
        pytest.skip("Vault not running or masterdata-api-key not seeded")
    return key.json()["data"]["data"]["value"]


def test_tms_store_loads_via_real_masterdata_call(masterdata_key):
    client = MasterdataClient(base_url=MASTERDATA_URL, api_key=masterdata_key)
    store = TmsStore(TMS_FIXTURES_DIR, client)
    assert len(store.list_routes()) == 8


def test_tms_store_rejects_unknown_location(tmp_path, masterdata_key):
    bad_routes = tmp_path / "routes.yaml"
    bad_routes.write_text(
        "routes:\n  - {id: BAD, lane: X-Y, legs: [{from: ZZZZZ, to: DEMUC, mode: rail, duration_days: 1}]}\n",
        encoding="utf-8",
    )
    (tmp_path / "route-availability.yaml").write_text(
        "route_availability:\n  - {route_id: BAD, status: available}\n", encoding="utf-8",
    )
    client = MasterdataClient(base_url=MASTERDATA_URL, api_key=masterdata_key)
    with pytest.raises(UnknownLocationError):
        TmsStore(tmp_path, client)


def test_tms_store_fails_closed_when_masterdata_unreachable():
    client = MasterdataClient(base_url="http://localhost:1", timeout=0.5)
    with pytest.raises(MasterdataUnavailableError):
        TmsStore(TMS_FIXTURES_DIR, client)
