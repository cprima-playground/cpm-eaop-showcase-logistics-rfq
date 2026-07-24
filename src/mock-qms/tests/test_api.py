from fastapi.testclient import TestClient

from mock_qms.api import build_app


def client():
    return TestClient(build_app())


def test_healthz():
    r = client().get("/healthz")
    assert r.status_code == 200
    assert r.json()["system"] == "Quote Management System (QMS)"


def test_swagger_ui_reachable():
    r = client().get("/swagger")
    assert r.status_code == 200
    assert "swagger" in r.text.lower()


def test_redoc_reachable():
    r = client().get("/redoc")
    assert r.status_code == 200


def test_openapi_schema_is_fastapi_generated_from_real_routes():
    """Every documented QMS path is a real route (null-op 501 bodies, but
    real request/response Pydantic models + x-domain-action/x-gap/x-consults
    via openapi_extra) -- the served schema is genuinely FastAPI-generated,
    not a hand-authored file (the former interfaces/api/qms.openapi.yaml,
    deleted -- a duplicate that would only drift, see mock_qms/api.py)."""
    r = client().get("/openapi.json")
    assert r.status_code == 200
    body = r.json()
    assert body["info"]["title"] == "Quote Management System (QMS)"
    assert body["info"]["version"] == "v0.1"  # rfq_common.app.create_app's default, not a hand-set draft version
    assert "/quotes" in body["paths"]
    assert "/quotes/{quoteId}/versions/{version}/price" in body["paths"]
    assert "QuoteVersion" in body["components"]["schemas"]
    assert "PricingResult" in body["components"]["schemas"]


def test_undocumented_endpoint_returns_501_not_implemented():
    r = client().post("/quotes", json={"rfq_id": "RFQ-1", "customer_id": "CUS-1", "currency": "EUR"})
    assert r.status_code == 501


def test_swagger_ui_shows_the_full_boundary():
    r = client().get("/swagger")
    assert r.status_code == 200
    schema = client().get("/openapi.json").json()
    assert len(schema["paths"]) >= 39  # 40 documented paths minus overlaps FastAPI dedupes by path (GET+POST share one path key)


def test_theme_css_endpoint_present():
    r = client().get("/_theme.css")
    assert r.status_code == 200
