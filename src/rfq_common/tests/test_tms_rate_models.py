"""Route/RouteEdge/RouteAvailability/CarrierRate validate against the REAL
fixtures (systems/tms/, systems/rate/) -- proves the models actually match
production data."""

from pathlib import Path

import yaml

from rfq_common.models import CarrierRate, Route, RouteAvailability, RouteEdge

RFQ_ROOT = Path(__file__).resolve().parents[3]


def test_real_edges_validate():
    doc = yaml.safe_load((RFQ_ROOT / "systems/tms/fixtures/edges.yaml").read_text(encoding="utf-8"))
    edges = [RouteEdge.model_validate(e) for e in doc["edges"]]
    assert len(edges) == 29
    assert edges[0].origin_id == "CNSHA"


def test_real_routes_validate():
    doc = yaml.safe_load((RFQ_ROOT / "systems/tms/fixtures/routes.yaml").read_text(encoding="utf-8"))
    routes = [Route.model_validate(r) for r in doc["routes"]]
    assert len(routes) == 17
    contracted = [r for r in routes if "contracted" in r.roles]
    assert len(contracted) == 1
    assert contracted[0].id == "SHA-HAM-MUC"
    assert routes[0].edges[0].edge_id == "OCEAN-CNSHA-DEHAM"


def test_real_route_availability_validates():
    doc = yaml.safe_load((RFQ_ROOT / "systems/tms/fixtures/route-availability.yaml").read_text(encoding="utf-8"))
    rows = [RouteAvailability.model_validate(a) for a in doc["route_availability"]]
    assert len(rows) == 17
    assert all(r.status == "available" for r in rows)


def test_real_carrier_rates_validate():
    doc = yaml.safe_load((RFQ_ROOT / "systems/rate/fixtures/rates.yaml").read_text(encoding="utf-8"))
    rates = [CarrierRate.model_validate(r) for r in doc["rates"]]
    assert len(rates) == 17
    sha_ham = next(r for r in rates if r.route_id == "SHA-HAM-MUC")
    assert sha_ham.carrier_id == "COSCO"
    assert sha_ham.currency == "CNY"
    assert sha_ham.base_cost == 42000
