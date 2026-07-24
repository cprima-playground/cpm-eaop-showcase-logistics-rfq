"""Route/RouteAvailability/CarrierRate validate against the REAL fixtures
(systems/tms/, systems/rate/) -- proves the models actually match production data."""

from pathlib import Path

import yaml

from rfq_common.models import CarrierRate, Route, RouteAvailability

RFQ_ROOT = Path(__file__).resolve().parents[3]


def test_real_routes_validate():
    doc = yaml.safe_load((RFQ_ROOT / "systems/tms/fixtures/routes.yaml").read_text(encoding="utf-8"))
    routes = [Route.model_validate(r) for r in doc["routes"]]
    assert len(routes) == 13
    contracted = [r for r in routes if r.contracted]
    assert len(contracted) == 1
    assert contracted[0].id == "SHA-HAM-MUC"
    assert routes[0].legs[0].from_ == "CNSHA"  # alias "from" -> from_


def test_real_route_availability_validates():
    doc = yaml.safe_load((RFQ_ROOT / "systems/tms/fixtures/route-availability.yaml").read_text(encoding="utf-8"))
    rows = [RouteAvailability.model_validate(a) for a in doc["route_availability"]]
    assert len(rows) == 13
    assert all(r.status == "available" for r in rows)


def test_real_carrier_rates_validate():
    doc = yaml.safe_load((RFQ_ROOT / "systems/rate/fixtures/rates.yaml").read_text(encoding="utf-8"))
    rates = [CarrierRate.model_validate(r) for r in doc["rates"]]
    assert len(rates) == 13
    sha_ham = next(r for r in rates if r.route_id == "SHA-HAM-MUC")
    assert sha_ham.carrier_id == "COSCO"
    assert sha_ham.currency == "CNY"
    assert sha_ham.base_cost == 42000
