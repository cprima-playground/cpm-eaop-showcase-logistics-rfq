"""Pure routing-math tests, migrated alongside route_geometry.py's own
logic (M10) -- same coverage tools/geo had. Deliberately never exercises
ocean_astar's real coastline A* pass here (slow, see conftest.py) -- only
dijkstra's graph-topology search and the pure geodesic/antimeridian math."""

from __future__ import annotations

from geo_api import routing


def test_dijkstra_finds_the_known_shanghai_hamburg_maritime_path(graph):
    path = routing.dijkstra(graph, "CNSHA", "DEHAM")
    assert path[0] == "CNSHA"
    assert path[-1] == "DEHAM"
    assert len(path) > 2  # real chokepoints in between, not a direct edge


def test_dijkstra_raises_graph_lookup_error_for_an_unknown_node(graph):
    import pytest
    with pytest.raises(routing.GraphLookupError):
        routing.dijkstra(graph, "CNSHA", "NOT-A-REAL-NODE")


def test_geodesic_segment_returns_endpoints_first_and_last():
    p1, p2 = (8.6, 50.1), (139.7, 35.7)  # Frankfurt -> Tokyo, lon/lat
    seg = routing.geodesic_segment(p1, p2)
    assert seg[0] == p1
    assert seg[-1] == p2
    assert len(seg) >= routing.MIN_POINTS


def test_geodesic_segment_of_a_zero_distance_leg_is_a_single_point():
    p = (10.0, 50.0)
    assert routing.geodesic_segment(p, p) == [p]


def test_split_antimeridian_passthrough_when_no_crossing():
    coords = [(10.0, 50.0), (20.0, 51.0), (30.0, 52.0)]
    segments = routing.split_antimeridian(coords)
    assert segments == [coords]


def test_split_antimeridian_splits_a_pacific_crossing_leg():
    # Shanghai (lon ~121E) -> Los Angeles (lon ~-118W): short way crosses +-180.
    coords = [(121.0, 31.0), (-118.0, 34.0)]
    segments = routing.split_antimeridian(coords)
    assert len(segments) == 2
    assert segments[0][0] == coords[0]
    assert segments[-1][-1] == coords[-1]
    # the split point sits on the +-180 seam on both sides
    assert abs(segments[0][-1][0]) == 180.0
    assert abs(segments[1][0][0]) == 180.0


def test_leg_to_geometry_is_a_linestring_when_no_antimeridian_crossing():
    coords = [(10.0, 50.0), (11.0, 51.0)]
    geometry = routing.leg_to_geometry(coords)
    assert geometry["type"] == "LineString"
    assert geometry["coordinates"] == [[10.0, 50.0], [11.0, 51.0]]


def test_leg_to_geometry_is_a_multilinestring_across_the_antimeridian():
    coords = [(121.0, 31.0), (-118.0, 34.0)]
    geometry = routing.leg_to_geometry(coords)
    assert geometry["type"] == "MultiLineString"
    assert len(geometry["coordinates"]) == 2


def test_leg_distance_km_of_two_identical_points_is_zero():
    assert routing.leg_distance_km([(10.0, 50.0)]) == 0.0


def test_routing_version_is_deterministic_for_unchanged_inputs(tmp_path):
    graph_file = tmp_path / "g.yaml"
    keepout_file = tmp_path / "k.yaml"
    graph_file.write_text("nodes: {}\n", encoding="utf-8")
    keepout_file.write_text("zones: []\n", encoding="utf-8")
    v1 = routing.routing_version(graph_file, keepout_file)
    v2 = routing.routing_version(graph_file, keepout_file)
    assert v1 == v2
    assert v1.endswith(f":{routing.ROUTING_ALGORITHM_VERSION}")


def test_routing_version_changes_when_graph_content_changes(tmp_path):
    graph_file = tmp_path / "g.yaml"
    keepout_file = tmp_path / "k.yaml"
    keepout_file.write_text("zones: []\n", encoding="utf-8")

    graph_file.write_text("nodes: {}\n", encoding="utf-8")
    v1 = routing.routing_version(graph_file, keepout_file)

    graph_file.write_text("nodes: {a: 1}\n", encoding="utf-8")
    v2 = routing.routing_version(graph_file, keepout_file)

    assert v1 != v2
