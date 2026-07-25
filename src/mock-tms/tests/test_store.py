from pathlib import Path

import pytest

from conftest import StubMasterdataClient
from mock_tms.store import InvalidTopologyError, TmsStore, location_serves_endpoint, parse_lane_id
from rfq_common.models import Route, RouteAvailability, RouteEdge, RouteEdgeRef

RFQ_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = RFQ_ROOT / "systems" / "tms" / "fixtures"


def store():
    return TmsStore(FIXTURES_DIR, StubMasterdataClient())


def test_loads_all_17_routes():
    assert len(store().list_routes()) == 17


def test_contracted_route():
    s = store()
    route = s.get_route("SHA-HAM-MUC")
    assert "contracted" in route.roles
    assert route.lane_id == "CNSHA-DEMUC"
    assert route.edges[0].edge_id == "OCEAN-CNSHA-DEHAM"


def test_contracted_shape_is_the_deliberate_minority():
    """Guardrail, not an incidental count: this showcase demonstrates AGENTIC
    remedies for non-contracted-lane deviations (D3, business/decisions.md) --
    that only works if most routes genuinely aren't contracted. Realistic
    freight economics agree: a shipper contracts its highest-volume core lane
    and leaves the long tail on spot (see KNOWN-ISSUES.md / this test's
    origin). If a future fixture edit marks more routes contracted, this
    fails loudly instead of silently eroding the demo's premise."""
    routes = store().list_routes()
    contracted = [r for r in routes if "contracted" in r.roles]
    assert len(contracted) == 1, (
        f"expected exactly 1 contracted route (the deliberate 80/20 shape), "
        f"got {len(contracted)}: {[r.id for r in contracted]}"
    )
    assert contracted[0].id == "SHA-HAM-MUC"
    non_contracted_share = 1 - (len(contracted) / len(routes))
    assert non_contracted_share >= 0.75, "non-contracted routes must stay the clear majority"


def test_transit_time_sums_legs():
    s = store()
    assert s.transit_time("SHA-HAM-MUC") == 27 + 2


def test_capacity_from_availability():
    s = store()
    assert s.capacity("SHA-HAM-MUC") == "available"


def test_feasible_lanes_filters_by_lane():
    """8 routes carry lane_id: CNSHA-DEMUC -- feasible_lanes groups by the
    raw `lane_id` field (mechanical, complete), with no separate curated
    subset (the old lane_alternatives list was removed -- dead, unread,
    and already stale). Includes the Baltic/Gdansk gateway (SHA-GDN-MUC)
    and the Cape-of-Good-Hope escalation (SHA-CPE-MUC) alongside the five
    North-Sea/Med alternatives."""
    s = store()
    lanes = s.feasible_lanes("CNSHA-DEMUC")
    assert len(lanes) == 8


def test_feasible_lanes_new_geography():
    """Geographic diversity: 3 new lanes outside the China->Germany corridor."""
    s = store()
    assert len(s.feasible_lanes("CNSHA-USLAX")) == 2   # transpacific: LA + Oakland
    assert len(s.feasible_lanes("AEJEA-DEHAM")) == 2   # Middle-East: Suez + Cape reroute
    assert len(s.feasible_lanes("NLRTM-ITMIL")) == 1   # intra-Europe: no alternative


def test_multi_leg_middle_east_reroute():
    s = store()
    route = s.get_route("MEA-CAPE")
    legs = s.resolve_legs(route)
    assert [leg["origin_id"] for leg in legs] == ["AEJEA", "ZADUR"]
    assert [leg["destination_id"] for leg in legs] == ["ZADUR", "DEHAM"]


def test_hamburg_has_overland_access_to_alternate_ocean_gateways():
    """Real new connectivity, not validation padding: DEHAM->NLRTM and
    DEHAM->BEANR are genuine overland feeder edges (Hamburg's hinterland
    rail access to the Rotterdam/Antwerp gateways), not legs invented only
    to satisfy the lane-endpoint check."""
    s = store()
    tat_rtm = s.get_route("TAT-RTM")
    tat_anr = s.get_route("TAT-ANR")
    assert s.resolve_legs(tat_rtm)[0] == {
        "origin_id": "DEHAM", "destination_id": "NLRTM", "mode": "rail", "indicative_duration_days": 1,
    }
    assert s.resolve_legs(tat_anr)[0] == {
        "origin_id": "DEHAM", "destination_id": "BEANR", "mode": "rail", "indicative_duration_days": 1,
    }


def test_oakland_route_connects_to_los_angeles_lane_destination():
    s = store()
    route = s.get_route("TPA-OAK")
    legs = s.resolve_legs(route)
    assert legs[-1]["destination_id"] == "USLAX"


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


# ------------------------------------------------------------- edge pool


def test_list_edges_returns_all_29_sorted():
    s = store()
    edges = s.list_edges()
    assert len(edges) == 29
    assert [e.id for e in edges] == sorted(e.id for e in edges)


def test_outgoing_and_incoming_edges_are_directed():
    s = store()
    outgoing = s.outgoing_edges("DEHAM")
    incoming = s.incoming_edges("DEHAM")
    assert any(e.destination_id == "DEMUC" for e in outgoing)
    assert any(e.origin_id == "CNSHA" for e in incoming)
    # directional: NLRTM->USNYC existing doesn't imply USNYC->NLRTM
    assert not any(e.origin_id == "USNYC" and e.destination_id == "NLRTM" for e in s.list_edges())


def test_edges_shared_by_multiple_routes():
    s = store()
    sharers = [r.id for r in s.list_routes() if any(ref.edge_id == "RAIL-DEHAM-DEMUC" for ref in r.edges)]
    assert set(sharers) == {"SHA-HAM-MUC", "NGB-HAM-MUC", "SHA-CPE-MUC"}


def test_route_resolution_is_a_direct_join_not_a_graph_search():
    """Route.edges is already the authoritative, ordered sequence --
    resolving it is an id lookup against the pool, never adjacency
    traversal. Removing an edge from the middle of the pool that a route
    doesn't use must not affect that route's resolution."""
    s = store()
    route = s.get_route("SHA-HAM-MUC")
    before = s.resolve_legs(route)
    # perturbing the store's edge index for an unrelated location must not
    # change this route's own resolved legs, since resolution never
    # consults outgoing_edges/incoming_edges.
    s._edges_by_origin.clear()
    after = s.resolve_legs(route)
    assert before == after


# ------------------------------------------------------------- validation


def test_parse_lane_id_rejects_malformed_ids():
    assert parse_lane_id("CNSHA-DEMUC") == ("CNSHA", "DEMUC")
    with pytest.raises(ValueError):
        parse_lane_id("CNSHA-DE-MUC")
    with pytest.raises(ValueError):
        parse_lane_id("CNSHA")


def test_location_serves_endpoint_exact_and_compatible():
    compat = {"CNSHA": ["CNPVG"]}
    assert location_serves_endpoint("CNSHA", "CNSHA", compat)
    assert location_serves_endpoint("CNPVG", "CNSHA", compat)
    assert not location_serves_endpoint("CNPVG", "DEMUC", compat)


def test_pvg_fra_muc_departs_via_endpoint_compatibility():
    """The one declared exception: CNPVG (airport) serving the CNSHA
    (seaport) lane -- not a mode-based carve-out."""
    s = store()
    route = s.get_route("PVG-FRA-MUC")
    legs = s.resolve_legs(route)
    assert legs[0]["origin_id"] == "CNPVG"
    assert route.lane_id == "CNSHA-DEMUC"


def test_duplicate_edge_id_rejected():
    edges = [
        RouteEdge(id="OCEAN-CNSHA-NLRTM", origin_id="CNSHA", destination_id="NLRTM", mode="ocean"),
        RouteEdge(id="OCEAN-CNSHA-NLRTM", origin_id="CNSHA", destination_id="BEANR", mode="ocean"),
    ]
    with pytest.raises(InvalidTopologyError):
        TmsStore._validate_edge_pool(edges)


def test_duplicate_edge_topology_rejected():
    edges = [
        RouteEdge(id="OCEAN-CNSHA-NLRTM", origin_id="CNSHA", destination_id="NLRTM", mode="ocean"),
        RouteEdge(id="OCEAN-CNSHA-NLRTM-DUP", origin_id="CNSHA", destination_id="NLRTM", mode="ocean"),
    ]
    with pytest.raises(InvalidTopologyError):
        TmsStore._validate_edge_pool(edges)


def test_edge_self_loop_rejected():
    edges = [RouteEdge(id="OCEAN-CNSHA-CNSHA", origin_id="CNSHA", destination_id="CNSHA", mode="ocean")]
    with pytest.raises(InvalidTopologyError):
        TmsStore._validate_edge_pool(edges)


def test_edge_id_must_match_its_own_fields():
    edges = [RouteEdge(id="OCEAN-CNSHA-DEHAM", origin_id="CNSHA", destination_id="NLRTM", mode="ocean")]
    with pytest.raises(InvalidTopologyError):
        TmsStore._validate_edge_pool(edges)


_AB = RouteEdge(id="OCEAN-AAAA-BBBB", origin_id="AAAA", destination_id="BBBB", mode="ocean")
_BC = RouteEdge(id="OCEAN-BBBB-CCCC", origin_id="BBBB", destination_id="CCCC", mode="ocean")
_CB = RouteEdge(id="OCEAN-CCCC-BBBB", origin_id="CCCC", destination_id="BBBB", mode="ocean")
_EDGES_BY_ID = {e.id: e for e in (_AB, _BC, _CB)}


def test_unknown_edge_reference_rejected():
    route = Route(id="R1", lane_id="AAAA-CCCC", edges=[RouteEdgeRef(edge_id="NOPE", indicative_duration_days=1)])
    with pytest.raises(InvalidTopologyError):
        TmsStore._validate_routes([route], _EDGES_BY_ID, {})


def test_discontinuous_route_rejected():
    route = Route(
        id="R1", lane_id="AAAA-BBBB",
        edges=[
            RouteEdgeRef(edge_id="OCEAN-AAAA-BBBB", indicative_duration_days=1),
            RouteEdgeRef(edge_id="OCEAN-CCCC-BBBB", indicative_duration_days=1),
        ],
    )
    with pytest.raises(InvalidTopologyError):
        TmsStore._validate_routes([route], _EDGES_BY_ID, {})


def test_repeated_location_rejected_simple_path_only():
    """A->B->C->B is a real cycle a typo could produce -- rejected even
    though no single edge repeats."""
    route = Route(
        id="R1", lane_id="AAAA-BBBB",
        edges=[
            RouteEdgeRef(edge_id="OCEAN-AAAA-BBBB", indicative_duration_days=1),
            RouteEdgeRef(edge_id="OCEAN-BBBB-CCCC", indicative_duration_days=1),
            RouteEdgeRef(edge_id="OCEAN-CCCC-BBBB", indicative_duration_days=1),
        ],
    )
    with pytest.raises(InvalidTopologyError):
        TmsStore._validate_routes([route], _EDGES_BY_ID, {})


def test_route_not_starting_at_lane_origin_rejected():
    route = Route(id="R1", lane_id="ZZZZ-BBBB", edges=[RouteEdgeRef(edge_id="OCEAN-AAAA-BBBB", indicative_duration_days=1)])
    with pytest.raises(InvalidTopologyError):
        TmsStore._validate_routes([route], _EDGES_BY_ID, {})


def test_route_not_ending_at_lane_destination_rejected():
    route = Route(id="R1", lane_id="AAAA-ZZZZ", edges=[RouteEdgeRef(edge_id="OCEAN-AAAA-BBBB", indicative_duration_days=1)])
    with pytest.raises(InvalidTopologyError):
        TmsStore._validate_routes([route], _EDGES_BY_ID, {})


def test_duplicate_route_id_rejected():
    route = Route(id="R1", lane_id="AAAA-BBBB", edges=[RouteEdgeRef(edge_id="OCEAN-AAAA-BBBB", indicative_duration_days=1)])
    with pytest.raises(InvalidTopologyError):
        TmsStore._validate_routes([route, route], _EDGES_BY_ID, {})


def test_route_endpoint_compatible_via_map_not_exact_match():
    route = Route(id="R1", lane_id="ZZZZ-BBBB", edges=[RouteEdgeRef(edge_id="OCEAN-AAAA-BBBB", indicative_duration_days=1)])
    # AAAA is declared compatible with lane origin ZZZZ -- passes without exact equality
    TmsStore._validate_routes([route], _EDGES_BY_ID, {"ZZZZ": ["AAAA"]})
