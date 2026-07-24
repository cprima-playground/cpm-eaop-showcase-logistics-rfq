from pathlib import Path

from mock_fx.store import FxStore

RFQ_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = RFQ_ROOT / "fixtures" / "fx"


def test_loads_both_real_fixtures():
    store = FxStore(FIXTURES_DIR)
    assert len(store._rates) == 2


def test_get_latest_when_no_effective_at():
    store = FxStore(FIXTURES_DIR)
    rate = store.get("CNY", "EUR")
    assert rate.rate == 0.1194  # today's, the latest snapshot
    assert rate.rate_ref == "FX-20260724-CNY-EUR"


def test_get_point_in_time_yesterday():
    store = FxStore(FIXTURES_DIR)
    rate = store.get("CNY", "EUR", effective_at="2026-07-23T12:00:00Z")
    assert rate.rate == 0.1226  # yesterday's snapshot, correctly picked
    assert rate.rate_ref == "FX-20260723-CNY-EUR"


def test_get_point_in_time_before_any_snapshot_returns_none():
    store = FxStore(FIXTURES_DIR)
    assert store.get("CNY", "EUR", effective_at="2020-01-01T00:00:00Z") is None


def test_get_unknown_pair_returns_none():
    store = FxStore(FIXTURES_DIR)
    assert store.get("USD", "JPY") is None


def test_reload_is_idempotent():
    store = FxStore(FIXTURES_DIR)
    before = len(store._rates)
    store.reload()
    assert len(store._rates) == before
