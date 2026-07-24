from pathlib import Path

from mock_fx import ecb_client
from mock_fx.generator import BAND_AMPLITUDE, NOISE_AMPLITUDE, generate_staircase
from mock_fx.store import HISTORY_DAYS, TOTAL_HISTORY_DAYS, FxStore, _parse

RFQ_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = RFQ_ROOT / "fixtures" / "fx"
FIXTURE_PAIRS = 4  # USD/GBP/JPY/CNY, all vs EUR


def test_loads_all_real_fixtures_plus_generated_history():
    store = FxStore(FIXTURES_DIR)
    # 2 real fixtures (today/yesterday) + 28 generated days, per pair -- see generator.py.
    assert len(store._rates) == FIXTURE_PAIRS * (2 + HISTORY_DAYS)


def test_get_latest_when_no_effective_at():
    store = FxStore(FIXTURES_DIR)
    rate = store.get("CNY", "EUR")
    assert rate.rate == 0.129791  # today's, the latest snapshot
    assert rate.rate_ref == "FX-20260724-CNY-EUR"


def test_get_point_in_time_yesterday():
    store = FxStore(FIXTURES_DIR)
    rate = store.get("CNY", "EUR", effective_at="2026-07-23T12:00:00Z")
    assert rate.rate == 0.129656  # yesterday's snapshot, correctly picked
    assert rate.rate_ref == "FX-20260723-CNY-EUR"


def test_get_point_in_time_before_any_snapshot_returns_none():
    store = FxStore(FIXTURES_DIR)
    assert store.get("CNY", "EUR", effective_at="2020-01-01T00:00:00Z") is None


def test_get_unknown_pair_returns_none():
    store = FxStore(FIXTURES_DIR)
    assert store.get("USD", "JPY") is None  # not a pair we hold -- only X/EUR


def test_reload_is_idempotent():
    store = FxStore(FIXTURES_DIR)
    before = len(store._rates)
    store.reload()
    assert len(store._rates) == before


def test_reload_regenerates_byte_identical_history():
    """Same seed (rfq_common.clock's default) -> same generated series, every
    reload -- required for RUNNING.md's reproducible-demo contract."""
    store = FxStore(FIXTURES_DIR)
    first = [r.rate for r in store.history("CNY", "EUR")]
    store.reload()
    second = [r.rate for r in store.history("CNY", "EUR")]
    assert first == second


def test_generated_history_stays_within_band():
    """Every synthetic point must stay comfortably under the D4 threshold
    (fx_variance_pct_x10 > 20, i.e. 2.0%) relative to its anchor (yesterday's
    real 0.129656) -- generated data must never itself look like a breakout."""
    store = FxStore(FIXTURES_DIR)
    anchor = 0.129656
    generated = store.history("CNY", "EUR")[:-2]  # exclude the 2 real fixtures
    assert len(generated) == HISTORY_DAYS
    max_allowed = BAND_AMPLITUDE + NOISE_AMPLITUDE
    for point in generated:
        deviation = abs(point.rate / anchor - 1)
        assert deviation <= max_allowed + 1e-9, f"{point.rate_ref}: {deviation} exceeds band"


def test_history_is_sorted_oldest_first_and_ends_with_real_fixtures():
    store = FxStore(FIXTURES_DIR)
    points = store.history("CNY", "EUR")
    assert len(points) == 2 + HISTORY_DAYS
    observed = [_parse(p.observed_at) for p in points]
    assert observed == sorted(observed)
    assert points[-2].rate == 0.129656  # yesterday
    assert points[-1].rate == 0.129791  # today, untouched, nominal


def test_history_days_param_via_api_layer_slices_from_the_end():
    store = FxStore(FIXTURES_DIR)
    all_points = store.history("CNY", "EUR")
    assert all_points[-5:][-1].rate == 0.129791  # slicing (done in api.py) keeps the latest


def test_generate_staircase_accumulates_past_threshold_without_any_single_step_doing_so():
    """Proves the generator CAN produce a cumulative-breakout pattern (several
    small steps that only cross the 2.0% D4 threshold together) -- a
    standalone capability test, not wired to a scenario pack (blocked on the
    not-yet-built scenario runner, see KNOWN-ISSUES.md)."""
    import random

    rng = random.Random(42)
    steps = generate_staircase(
        "CNY/EUR", anchor_rate=0.129656, before=_parse("2026-07-23T08:00:00Z"),
        steps=5, step_pct=0.006, rng=rng,
    )
    assert len(steps) == 5
    for i in range(1, len(steps)):
        single_step_pct = abs(steps[i].rate / steps[i - 1].rate - 1)
        assert single_step_pct < 0.02, "no individual step should itself look like a breakout"
    cumulative_pct = abs(steps[-1].rate / 0.129656 - 1)
    assert cumulative_pct > 0.02, "the cumulative move must cross the D4 threshold (fx_variance_pct_x10 > 20)"


# --- live ECB anchor (opt-out at the api.py boundary; FxStore itself defaults
# to live_anchor=False so direct construction, as used throughout this file
# and in tests generally, stays hermetic/offline) --------------------------

_SAMPLE_ECB_DAYS = [
    ("2026-07-23", {"USD": 1.1392, "GBP": 0.85318, "JPY": 186.23, "CNY": 7.7127}),
    ("2026-07-24", {"USD": 1.1377, "GBP": 0.85388, "JPY": 186.38, "CNY": 7.7047}),
]


def test_live_anchor_uses_fetched_ecb_rates_when_reachable(monkeypatch):
    monkeypatch.setattr(ecb_client, "fetch_history", lambda currencies: _SAMPLE_ECB_DAYS)
    store = FxStore(FIXTURES_DIR, live_anchor=True)
    rate = store.get("CNY", "EUR")
    assert rate.rate == round(1 / 7.7047, 6)
    assert rate.source == "ecb-eurofxref"
    # 2 days * 4 currencies -- the generator/fixture path is bypassed entirely.
    assert len(store._rates) == 2 * 4


def test_live_anchor_falls_back_to_fixtures_when_ecb_unreachable(monkeypatch):
    def _raise(currencies):
        raise ecb_client.EcbUnavailableError("network down")

    monkeypatch.setattr(ecb_client, "fetch_history", _raise)
    store = FxStore(FIXTURES_DIR, live_anchor=True)
    rate = store.get("CNY", "EUR")
    assert rate.rate == 0.129791  # the committed fixture, not an ECB value
    assert rate.source == "corporate-fx-service"


def test_live_anchor_falls_back_to_cache_file_when_ecb_unreachable(monkeypatch, tmp_path):
    def _raise(currencies):
        raise ecb_client.EcbUnavailableError("network down")

    def _from_file(path, currencies):
        assert Path(path) == cache_file
        return _SAMPLE_ECB_DAYS

    cache_file = tmp_path / "ecb-hist-cache.xml"
    cache_file.write_text("<fake/>", encoding="utf-8")
    monkeypatch.setattr(ecb_client, "fetch_history", _raise)
    monkeypatch.setattr(ecb_client, "load_history_from_file", _from_file)

    store = FxStore(FIXTURES_DIR, live_anchor=True, ecb_cache_file=cache_file)
    rate = store.get("CNY", "EUR")
    assert rate.rate == round(1 / 7.7047, 6)
    assert rate.source == "ecb-eurofxref"


def test_live_anchor_falls_back_to_fixtures_when_cache_file_also_unusable(monkeypatch, tmp_path):
    def _raise(currencies):
        raise ecb_client.EcbUnavailableError("network down")

    monkeypatch.setattr(ecb_client, "fetch_history", _raise)
    store = FxStore(FIXTURES_DIR, live_anchor=True, ecb_cache_file=tmp_path / "missing.xml")
    rate = store.get("CNY", "EUR")
    assert rate.rate == 0.129791  # the committed fixture


def test_live_anchor_slices_to_total_history_days(monkeypatch):
    days = [(f"2026-05-{d:02d}", {"CNY": 7.7}) for d in range(1, 32)] + \
           [(f"2026-06-{d:02d}", {"CNY": 7.7}) for d in range(1, 9)]  # 39 days, more than needed
    monkeypatch.setattr(ecb_client, "fetch_history", lambda currencies: days)
    store = FxStore(FIXTURES_DIR, live_anchor=True)
    assert len(store.history("CNY", "EUR")) == TOTAL_HISTORY_DAYS
