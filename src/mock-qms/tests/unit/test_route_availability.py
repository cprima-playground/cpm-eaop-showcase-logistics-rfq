"""Commercial Preconditions (ADR-011): QMS honors TMS's route-executability
truth at price_version() time -- stub-based, offline. See
tests/business/test_scenario_hamburg_closure.py for the live end-to-end
version of this same business rule."""

from fastapi.testclient import TestClient

from conftest import TEST_API_KEY as API_KEY
from conftest import StubTmsClient
from mock_qms.api import build_app


def client():
    return TestClient(build_app())


def _create_quote(c):
    return c.post(
        "/quotes", headers={"X-API-Key": API_KEY},
        json={"rfq_id": "RFQ-9001", "customer_id": "ACME", "currency": "EUR"},
    ).json()


def _compose(c, quote_id, version, route_id="SHA-HAM-MUC"):
    c.put(
        f"/quotes/{quote_id}/versions/{version}/route-recommendation", headers={"X-API-Key": API_KEY},
        json={"recommendation_id": "REC-9001-v1", "selected_route_id": route_id},
    )
    c.put(
        f"/quotes/{quote_id}/versions/{version}/pricing-inputs", headers={"X-API-Key": API_KEY},
        json={
            "fx_rate_ref": "FX-20260724-CNY-EUR", "rate_refs": [route_id],
            "pricing_terms_ref": "PT-1", "margin_floor_ref": "standard",
        },
    )


def test_pricing_succeeds_when_tms_reports_available():
    c = client()
    q = _create_quote(c)
    _compose(c, q["quote_id"], 1)
    r = c.post(f"/quotes/{q['quote_id']}/versions/1/price", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200


def test_pricing_succeeds_unflagged_when_tms_reports_limited():
    StubTmsClient._states["SHA-HAM-MUC"] = {"route_id": "SHA-HAM-MUC", "status": "limited"}
    c = client()
    q = _create_quote(c)
    _compose(c, q["quote_id"], 1)
    r = c.post(f"/quotes/{q['quote_id']}/versions/1/price", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200


def test_pricing_succeeds_unflagged_when_tms_reports_degraded():
    StubTmsClient._states["SHA-HAM-MUC"] = {"route_id": "SHA-HAM-MUC", "status": "degraded"}
    c = client()
    q = _create_quote(c)
    _compose(c, q["quote_id"], 1)
    r = c.post(f"/quotes/{q['quote_id']}/versions/1/price", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200


def test_pricing_rejected_when_tms_reports_unavailable():
    StubTmsClient._states["SHA-HAM-MUC"] = {"route_id": "SHA-HAM-MUC", "status": "unavailable", "reason": "port congestion"}
    c = client()
    q = _create_quote(c)
    _compose(c, q["quote_id"], 1)
    r = c.post(f"/quotes/{q['quote_id']}/versions/1/price", headers={"X-API-Key": API_KEY})
    assert r.status_code == 409
    assert "commercial precondition" in r.text
    assert "route" in r.text and "not established" in r.text
    assert "unavailable" in r.text


def test_pricing_rejected_when_tms_has_no_record_of_route():
    c = client()
    q = _create_quote(c)
    _compose(c, q["quote_id"], 1, route_id="NO-SUCH-ROUTE")
    r = c.post(f"/quotes/{q['quote_id']}/versions/1/price", headers={"X-API-Key": API_KEY})
    assert r.status_code == 409
    assert "no record" in r.text


def test_price_version_requires_tms_configured(monkeypatch):
    import mock_qms.api as api_module

    monkeypatch.setattr(api_module, "_tms_client", lambda: (_ for _ in ()).throw(RuntimeError("no tms")))
    c = TestClient(api_module.build_app())
    q = _create_quote(c)
    _compose(c, q["quote_id"], 1)
    r = c.post(f"/quotes/{q['quote_id']}/versions/1/price", headers={"X-API-Key": API_KEY})
    assert r.status_code == 400
    assert "tms" in r.text
