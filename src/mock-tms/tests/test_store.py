from pathlib import Path

from conftest import StubMasterdataClient
from mock_tms.store import TmsStore
from rfq_common.models import RouteAvailability

RFQ_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = RFQ_ROOT / "systems" / "tms" / "fixtures"


def store():
    return TmsStore(FIXTURES_DIR, StubMasterdataClient())


def test_loads_all_13_routes():
    assert len(store().list_routes()) == 13


def test_contracted_route():
    s = store()
    route = s.get_route("SHA-HAM-MUC")
    assert route.contracted is True
    assert route.lane == "CNSHA-DEMUC"
    assert route.legs[0].from_ == "CNSHA"


def test_transit_time_sums_legs():
    s = store()
    assert s.transit_time("SHA-HAM-MUC") == 27 + 2


def test_capacity_from_availability():
    s = store()
    assert s.capacity("SHA-HAM-MUC") == "available"


def test_feasible_lanes_filters_by_lane():
    """7, not 6: feasible_lanes groups by the raw `lane` field (mechanical,
    complete) -- routes.yaml's curated `lane_alternatives` list is a narrower,
    business-curated subset (excludes the Baltic/Gdansk gateway) that this
    store doesn't currently expose separately."""
    s = store()
    lanes = s.feasible_lanes("CNSHA-DEMUC")
    assert len(lanes) == 7


def test_feasible_lanes_new_geography():
    """Geographic diversity: 3 new lanes outside the China->Germany corridor."""
    s = store()
    assert len(s.feasible_lanes("CNSHA-USLAX")) == 2   # transpacific: LA + Oakland
    assert len(s.feasible_lanes("AEJEA-DEHAM")) == 2   # Middle-East: Suez + Cape reroute
    assert len(s.feasible_lanes("NLRTM-ITMIL")) == 1   # intra-Europe: no alternative


def test_multi_leg_middle_east_reroute():
    s = store()
    route = s.get_route("MEA-CAPE")
    assert [leg.from_ for leg in route.legs] == ["AEJEA", "ZADUR"]
    assert [leg.to for leg in route.legs] == ["ZADUR", "DEHAM"]


def test_unknown_route_returns_none():
    s = store()
    assert s.get_route("NOPE") is None
    assert s.transit_time("NOPE") is None
    assert s.capacity("NOPE") is None


def test_reload_is_idempotent():
    s = store()
    before = len(s.list_routes())
    s.reload()
    assert len(s.list_routes()) == before


def test_set_availability_mutates_live_state():
    s = store()
    s.set_availability("SHA-HAM-MUC", RouteAvailability(route_id="SHA-HAM-MUC", status="unavailable", reason="port congestion"))
    assert s.capacity("SHA-HAM-MUC") == "unavailable"
    assert s.availability("SHA-HAM-MUC").reason == "port congestion"


def test_reload_discards_set_availability_mutation():
    s = store()
    s.set_availability("SHA-HAM-MUC", RouteAvailability(route_id="SHA-HAM-MUC", status="unavailable"))
    s.reload()
    assert s.capacity("SHA-HAM-MUC") == "available"
