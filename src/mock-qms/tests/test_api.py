from fastapi.testclient import TestClient

from conftest import TEST_API_KEY as API_KEY
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
    """Every documented QMS path is a real route -- most still null-op 501
    (Cedar/pricing math not built), but Quotes/Versions are now backed by a
    real store (see mock_qms/store.py). The served schema is genuinely
    FastAPI-generated, not a hand-authored file (the former
    interfaces/api/qms.openapi.yaml, deleted -- a duplicate that would only
    drift, see mock_qms/api.py)."""
    r = client().get("/openapi.json")
    assert r.status_code == 200
    body = r.json()
    assert body["info"]["title"] == "Quote Management System (QMS)"
    assert body["info"]["version"] == "v0.1"  # rfq_common.app.create_app's default, not a hand-set draft version
    assert "/quotes" in body["paths"]
    assert "/quotes/{quoteId}/versions/{version}/price" in body["paths"]
    assert "QuoteVersion" in body["components"]["schemas"]
    assert "PricingResult" in body["components"]["schemas"]


def test_still_undocumented_endpoint_returns_501_not_implemented():
    """Pricing (D16, R1-R6 math) genuinely isn't built -- distinct from the
    Quotes/Versions CRUD below, which now is."""
    r = client().post("/quotes/Q-9999/versions/1/price", headers={"X-API-Key": API_KEY})
    assert r.status_code == 501


def test_swagger_ui_shows_the_full_boundary():
    r = client().get("/swagger")
    assert r.status_code == 200
    schema = client().get("/openapi.json").json()
    assert len(schema["paths"]) >= 39  # 40 documented paths minus overlaps FastAPI dedupes by path (GET+POST share one path key)


def test_theme_css_endpoint_present():
    r = client().get("/_theme.css")
    assert r.status_code == 200


def test_create_quote_requires_api_key():
    assert client().post("/quotes", json={"rfq_id": "RFQ-1", "customer_id": "ACME", "currency": "EUR"}).status_code == 401


def test_create_quote():
    r = client().post(
        "/quotes", headers={"X-API-Key": API_KEY},
        json={"rfq_id": "RFQ-1001", "customer_id": "ACME", "currency": "EUR"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["version"] == 1
    assert body["status"] == "draft"
    assert body["quote_id"].startswith("Q-")


def test_create_quote_unknown_customer_400():
    r = client().post(
        "/quotes", headers={"X-API-Key": API_KEY},
        json={"rfq_id": "RFQ-1001", "customer_id": "NOPE", "currency": "EUR"},
    )
    assert r.status_code == 400


def test_get_quote_roundtrip():
    c = client()
    created = c.post(
        "/quotes", headers={"X-API-Key": API_KEY},
        json={"rfq_id": "RFQ-1001", "customer_id": "ACME", "currency": "EUR"},
    ).json()
    r = c.get(f"/quotes/{created['quote_id']}", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert r.json()["customer_id"] == "ACME"
    assert r.json()["latest_version"] == 1


def test_get_unknown_quote_404():
    r = client().get("/quotes/Q-NOPE", headers={"X-API-Key": API_KEY})
    assert r.status_code == 404


def test_supersede_appends_a_new_version():
    c = client()
    v1 = c.post(
        "/quotes", headers={"X-API-Key": API_KEY},
        json={"rfq_id": "RFQ-1001", "customer_id": "ACME", "currency": "EUR"},
    ).json()
    r = c.post(
        f"/quotes/{v1['quote_id']}/versions", headers={"X-API-Key": API_KEY, "Idempotency-Key": "k1"},
        json={"prior_version": 1, "expected_latest_version": 1, "change_reason": "route_unavailable"},
    )
    assert r.status_code == 201
    v2 = r.json()
    assert v2["version"] == 2
    assert v2["prior_version"] == 1

    versions = c.get(f"/quotes/{v1['quote_id']}/versions", headers={"X-API-Key": API_KEY}).json()
    assert [v["version"] for v in versions] == [1, 2]

    # v1 itself is untouched -- append-only, never mutated
    v1_reread = c.get(f"/quotes/{v1['quote_id']}/versions/1", headers={"X-API-Key": API_KEY}).json()
    assert v1_reread["status"] == "draft"


def test_supersede_stale_precondition_is_409_not_403():
    c = client()
    v1 = c.post(
        "/quotes", headers={"X-API-Key": API_KEY},
        json={"rfq_id": "RFQ-1001", "customer_id": "ACME", "currency": "EUR"},
    ).json()
    r = c.post(
        f"/quotes/{v1['quote_id']}/versions", headers={"X-API-Key": API_KEY, "Idempotency-Key": "k1"},
        json={"prior_version": 5, "expected_latest_version": 5},
    )
    assert r.status_code == 409


def test_search_quotes_by_customer():
    c = client()
    c.post("/quotes", headers={"X-API-Key": API_KEY}, json={"rfq_id": "RFQ-1", "customer_id": "ACME", "currency": "EUR"})
    c.post("/quotes", headers={"X-API-Key": API_KEY}, json={"rfq_id": "RFQ-2", "customer_id": "COSCO", "currency": "EUR"})
    r = c.get("/quotes", headers={"X-API-Key": API_KEY}, params={"customerId": "ACME"})
    assert r.status_code == 200
    assert all(q["customer_id"] == "ACME" for q in r.json())


def test_timeline_reflects_version_history():
    c = client()
    v1 = c.post(
        "/quotes", headers={"X-API-Key": API_KEY},
        json={"rfq_id": "RFQ-1001", "customer_id": "ACME", "currency": "EUR"},
    ).json()
    c.post(
        f"/quotes/{v1['quote_id']}/versions", headers={"X-API-Key": API_KEY, "Idempotency-Key": "k1"},
        json={"prior_version": 1, "expected_latest_version": 1},
    )
    r = c.get(f"/quotes/{v1['quote_id']}/timeline", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert [t["version"] for t in r.json()] == [1, 2]


# systems/qms/fixtures/quotes.yaml: 10 quotes, versions sum to 19 (3+1+2+1+4+1+2+1+1+3)
BASELINE_COUNT = 10 + 19


def test_baseline_fixture_is_seeded_at_boot():
    r = client().get("/admin/stats", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert r.json()["count"] == BASELINE_COUNT


def test_admin_reset_discards_session_growth_back_to_baseline():
    c = client()
    c.post("/quotes", headers={"X-API-Key": API_KEY}, json={"rfq_id": "RFQ-1", "customer_id": "ACME", "currency": "EUR"})
    assert c.get("/admin/stats", headers={"X-API-Key": API_KEY}).json()["count"] == BASELINE_COUNT + 2  # 1 quote + 1 version

    r = c.post("/admin/reset", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert c.get("/admin/stats", headers={"X-API-Key": API_KEY}).json()["count"] == BASELINE_COUNT


def test_admin_stats_shape():
    r = client().get("/admin/stats", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == BASELINE_COUNT
    assert body["approx_bytes"] > 0


def test_baseline_quote_has_a_real_supersede_chain():
    r = client().get("/quotes/Q-1001/versions", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    versions = r.json()
    assert [v["version"] for v in versions] == [1, 2, 3]
    assert versions[0]["prior_version"] is None
    assert versions[2]["prior_version"] == 2


def test_baseline_quote_is_readable():
    r = client().get("/quotes/Q-1001", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert r.json()["customer_id"] == "ACME"
