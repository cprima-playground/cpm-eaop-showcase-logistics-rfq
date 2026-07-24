from pathlib import Path

import pytest
from conftest import StubMasterdataClient
from mock_rate.store import RateStore, UnknownCarrierError, UnknownCurrencyError

RFQ_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = RFQ_ROOT / "systems" / "rate" / "fixtures"


def store():
    return RateStore(FIXTURES_DIR, StubMasterdataClient())


def test_loads_all_8_rates():
    assert len(store().list()) == 8


def test_get_rate_sha_ham_muc():
    rate = store().get_rate("SHA-HAM-MUC")
    assert rate.carrier_id == "COSCO"
    assert rate.currency == "CNY"
    assert rate.base_cost == 42000


def test_surcharges():
    assert store().surcharges("SHA-HAM-MUC") == 5100


def test_unknown_route_returns_none():
    s = store()
    assert s.get_rate("NOPE") is None
    assert s.surcharges("NOPE") is None


def test_rejects_carrier_not_in_masterdata(tmp_path):
    bad = tmp_path / "rates.yaml"
    bad.write_text(
        "rates:\n  - {route_id: X, carrier_id: NOT-A-CARRIER, currency: EUR, base_cost: 1, surcharges: 0, capacity_status: available}\n",
        encoding="utf-8",
    )
    with pytest.raises(UnknownCarrierError):
        RateStore(tmp_path, StubMasterdataClient())


def test_rejects_customer_used_as_carrier(tmp_path):
    """ACME is a real Party but kind=customer, not carrier -- must still reject."""
    bad = tmp_path / "rates.yaml"
    bad.write_text(
        "rates:\n  - {route_id: X, carrier_id: ACME, currency: EUR, base_cost: 1, surcharges: 0, capacity_status: available}\n",
        encoding="utf-8",
    )
    with pytest.raises(UnknownCarrierError):
        RateStore(tmp_path, StubMasterdataClient())


def test_rejects_unknown_currency(tmp_path):
    bad = tmp_path / "rates.yaml"
    bad.write_text(
        "rates:\n  - {route_id: X, carrier_id: COSCO, currency: ZZZ, base_cost: 1, surcharges: 0, capacity_status: available}\n",
        encoding="utf-8",
    )
    with pytest.raises(UnknownCurrencyError):
        RateStore(tmp_path, StubMasterdataClient())


def test_reload_is_idempotent():
    s = store()
    before = len(s.list())
    s.reload()
    assert len(s.list()) == before
