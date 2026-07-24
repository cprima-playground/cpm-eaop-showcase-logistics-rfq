from fastapi.testclient import TestClient

from mock_fx.api import build_app
from conftest import TEST_API_KEY as API_KEY


def client():
    return TestClient(build_app())


def test_healthz():
    r = client().get("/healthz")
    assert r.status_code == 200


def test_swagger_ui_is_reachable():
    """Answers 'is there a Swagger UI' -- yes, and it's actually live here."""
    r = client().get("/docs")
    assert r.status_code == 200
    assert "swagger" in r.text.lower()


def test_openapi_schema_reachable():
    r = client().get("/openapi.json")
    assert r.status_code == 200
    assert r.json()["info"]["title"] == "Mock Corporate FX Service"


def test_get_rate_requires_api_key():
    r = client().get("/exchange-rates/CNY/EUR")
    assert r.status_code == 401


def test_get_rate_rejects_wrong_key():
    r = client().get("/exchange-rates/CNY/EUR", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_get_rate_with_valid_key():
    r = client().get("/exchange-rates/CNY/EUR", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    body = r.json()
    assert body["pair"] == "CNY/EUR"
    assert body["rate"] == 0.1194
    assert body["rate_ref"] == "FX-20260724-CNY-EUR"


def test_get_rate_point_in_time():
    r = client().get(
        "/exchange-rates/CNY/EUR",
        params={"effectiveAt": "2026-07-23T12:00:00Z"},
        headers={"X-API-Key": API_KEY},
    )
    assert r.status_code == 200
    assert r.json()["rate"] == 0.1226


def test_get_rate_malformed_effective_at_returns_400_not_500():
    r = client().get(
        "/exchange-rates/CNY/EUR",
        params={"effectiveAt": "not-a-date"},
        headers={"X-API-Key": API_KEY},
    )
    assert r.status_code == 400


def test_get_rate_unknown_pair_404():
    r = client().get("/exchange-rates/USD/JPY", headers={"X-API-Key": API_KEY})
    assert r.status_code == 404


def test_admin_reset():
    r = client().post("/admin/reset", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert r.json()["status"] == "reset"


def test_theme_css_endpoint_present():
    r = client().get("/_theme.css")
    assert r.status_code == 200


# --- /convert -- fractional-unit handling via masterdata (ADR-010) ------------

def test_convert_cny_to_eur():
    r = client().get(
        "/convert",
        params={"amount": "42000", "from_currency": "CNY", "to_currency": "EUR"},
        headers={"X-API-Key": API_KEY},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["converted_amount"] == "5014.80"  # 42000 * 0.1194, 2 decimals
    assert body["minor_unit"] == 2


def test_convert_inverse_direction_eur_to_cny():
    r = client().get(
        "/convert",
        params={"amount": "100", "from_currency": "EUR", "to_currency": "CNY"},
        headers={"X-API-Key": API_KEY},
    )
    assert r.status_code == 200
    # inverse of CNY/EUR=0.1194 -> 100 / 0.1194 ~= 837.52, rounded to CNY's 2 decimals
    assert r.json()["minor_unit"] == 2


def test_convert_unknown_currency_400():
    r = client().get(
        "/convert",
        params={"amount": "100", "from_currency": "CNY", "to_currency": "ZZZ"},
        headers={"X-API-Key": API_KEY},
    )
    assert r.status_code == 400


def test_convert_malformed_amount_400():
    r = client().get(
        "/convert",
        params={"amount": "not-a-number", "from_currency": "CNY", "to_currency": "EUR"},
        headers={"X-API-Key": API_KEY},
    )
    assert r.status_code == 400


def test_convert_no_rate_404():
    r = client().get(
        "/convert",
        params={"amount": "100", "from_currency": "USD", "to_currency": "JPY"},
        headers={"X-API-Key": API_KEY},
    )
    assert r.status_code == 404


def test_convert_requires_api_key():
    r = client().get("/convert", params={"amount": "1", "from_currency": "CNY", "to_currency": "EUR"})
    assert r.status_code == 401
