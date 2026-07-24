"""Proves FX genuinely consumes masterdata via its REST API (ADR-010) -- not a
stub, not a duplicated file. Skips (not fails) if masterdata isn't running,
same discipline as the Vault/PDP live suites.
"""

from pathlib import Path

import httpx
import pytest

from mock_fx.store import FxStore, UnknownCurrencyError
from rfq_common.masterdata_client import MasterdataClient, MasterdataUnavailableError

MASTERDATA_URL = "http://localhost:8003"
RFQ_ROOT = Path(__file__).resolve().parents[3]
FX_FIXTURES_DIR = RFQ_ROOT / "fixtures" / "fx"


def _masterdata_up() -> bool:
    try:
        return httpx.get(f"{MASTERDATA_URL}/healthz", timeout=1.0).status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="module")
def masterdata_key():
    if not _masterdata_up():
        pytest.skip(f"masterdata not running on {MASTERDATA_URL} (uv run mock-masterdata serve --port 8003)")
    key = httpx.get(
        "http://localhost:8200/v1/secret/data/rfq/masterdata-api-key",
        headers={"X-Vault-Token": "rfq-dev-root"},
        timeout=5.0,
    )
    if key.status_code != 200:
        pytest.skip("Vault not running or masterdata-api-key not seeded (uv run seed.py in infra/vault/)")
    return key.json()["data"]["data"]["value"]


def test_fx_store_loads_via_real_masterdata_call(masterdata_key):
    """The real proof: no local currency list, no stub -- FxStore's validation
    genuinely round-trips through masterdata's HTTP API."""
    client = MasterdataClient(base_url=MASTERDATA_URL, api_key=masterdata_key)
    store = FxStore(FX_FIXTURES_DIR, client)
    assert store.minor_unit("EUR") == 2
    assert store.minor_unit("JPY") == 0  # real masterdata data, not assumed


def test_fx_store_rejects_currency_masterdata_does_not_know(tmp_path, masterdata_key):
    """An unknown currency in a fixture -> genuine rejection via the real API,
    not a silent pass."""
    bad_fixture = tmp_path / "bad.json"
    bad_fixture.write_text(
        '{"pair": "ZZZ/EUR", "rate": 1.0, "observed_at": "2026-01-01T00:00:00Z", "rate_ref": "test"}',
        encoding="utf-8",
    )
    client = MasterdataClient(base_url=MASTERDATA_URL, api_key=masterdata_key)
    with pytest.raises(UnknownCurrencyError):
        FxStore(tmp_path, client)


def test_fx_store_fails_closed_when_masterdata_unreachable():
    """Wrong port -> unreachable -> raises, never silently skips validation."""
    client = MasterdataClient(base_url="http://localhost:1", timeout=0.5)
    with pytest.raises(MasterdataUnavailableError):
        FxStore(FX_FIXTURES_DIR, client)
