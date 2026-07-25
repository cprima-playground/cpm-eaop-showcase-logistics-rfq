"""Offline UI tests for the QMS frontend (/app/*) -- role-gate redirect/403,
live-section assertions, empty-state-panel assertions for stub sections.
Principal is monkeypatched onto mock_qms.api._current_principal, same
pattern ops-dashboard's own tests/test_api.py uses (module-level function,
not a build_app() closure -- see api.py's own docstring on why)."""

from fastapi.testclient import TestClient

import mock_qms.api as api_module
from rfq_common.identity import Principal

READER = Principal(kind="human", id="diane.delgado", roles=["reader"])
COMMERCIAL_MANAGER = Principal(
    kind="human", id="mona.commercial", roles=["reader", "commercial-manager"],
    manager="diane.delgado", approval_limit_eur_cents=1000000,
)
PRICING_MANAGER = Principal(kind="human", id="sam.pricing", roles=["reader", "pricing-manager"])
ADMIN = Principal(kind="human", id="aiden.ashford", roles=["reader", "administrator"])
NO_ROLE = Principal(kind="human", id="bob", roles=[])


def client() -> TestClient:
    return TestClient(api_module.build_app())


def _as(monkeypatch, principal):
    monkeypatch.setattr(api_module, "_current_principal", lambda request: principal)


# --------------------------------------------------------------- role gates

def test_dashboard_redirects_anonymous_to_login(monkeypatch):
    _as(monkeypatch, None)
    r = client().get("/app", follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    assert r.headers["location"] == "/login"


def test_dashboard_403_without_reader_role(monkeypatch):
    _as(monkeypatch, NO_ROLE)
    assert client().get("/app").status_code == 403


def test_approvals_requires_commercial_manager(monkeypatch):
    _as(monkeypatch, READER)
    assert client().get("/app/approvals").status_code == 403
    _as(monkeypatch, COMMERCIAL_MANAGER)
    assert client().get("/app/approvals").status_code == 200


def test_pricing_config_requires_pricing_manager(monkeypatch):
    _as(monkeypatch, READER)
    assert client().get("/app/pricing-config").status_code == 403
    _as(monkeypatch, PRICING_MANAGER)
    assert client().get("/app/pricing-config").status_code == 200


# --------------------------------------------------------------- live sections

def test_dashboard_shows_real_kpi_counts(monkeypatch):
    _as(monkeypatch, READER)
    r = client().get("/app")
    assert r.status_code == 200
    assert ">10<" in r.text  # baseline fixture: 10 quotes
    assert ">0<" in r.text  # approval_required count, correctly zero today


def test_quotes_list_shows_real_search(monkeypatch):
    _as(monkeypatch, READER)
    c = client()
    r = c.get("/app/quotes")
    assert r.status_code == 200
    assert r.text.count("/app/quotes/Q-") >= 10

    filtered = c.get("/app/quotes", params={"customerId": "NOPE"})
    assert "No quotes match this search" in filtered.text


def test_quote_detail_shows_live_header_and_timeline(monkeypatch):
    _as(monkeypatch, READER)
    r = client().get("/app/quotes/Q-1001")
    assert r.status_code == 200
    assert "Q-1001" in r.text
    assert "ACME" in r.text
    assert r.text.count("v1") >= 1
    assert r.text.count("v2") >= 1  # Q-1001 is seeded with versions: 3


def test_quote_detail_unknown_quote_404(monkeypatch):
    _as(monkeypatch, READER)
    assert client().get("/app/quotes/Q-NOPE").status_code == 404


def test_approval_limit_badge_shown_for_commercial_manager(monkeypatch):
    _as(monkeypatch, COMMERCIAL_MANAGER)
    r = client().get("/app")
    assert "Your approval limit" in r.text
    assert "10,000" in r.text


def test_approval_limit_badge_absent_for_plain_reader(monkeypatch):
    _as(monkeypatch, READER)
    r = client().get("/app")
    assert "Your approval limit" not in r.text


def test_org_chart_shows_all_four_people(monkeypatch):
    _as(monkeypatch, ADMIN)
    r = client().get("/app/org")
    assert r.status_code == 200
    for name in ("Diane Delgado", "Mona Caldwell", "Marek Petrov", "Aiden Ashford"):
        assert name in r.text


# --------------------------------------------------------------- empty states

def test_quote_detail_shows_empty_state_for_stub_sections(monkeypatch):
    _as(monkeypatch, READER)
    r = client().get("/app/quotes/Q-1001")
    assert "not implemented" in r.text
    assert "not available yet" in r.text  # Decision Evidence rows


def test_quote_detail_decision_actions_disabled_for_commercial_manager(monkeypatch):
    _as(monkeypatch, COMMERCIAL_MANAGER)
    r = client().get("/app/quotes/Q-1001")
    assert "Approve" in r.text
    assert "disabled" in r.text


def test_quote_detail_decision_actions_hidden_for_plain_reader(monkeypatch):
    _as(monkeypatch, READER)
    r = client().get("/app/quotes/Q-1001")
    assert "Decision actions require the commercial-manager role" in r.text


def test_customer_view_is_empty_state(monkeypatch):
    _as(monkeypatch, READER)
    r = client().get("/app/quotes/Q-1001/customer-view")
    assert r.status_code == 200
    assert "not implemented" in r.text


def test_pricing_config_is_empty_state(monkeypatch):
    _as(monkeypatch, PRICING_MANAGER)
    r = client().get("/app/pricing-config")
    assert "not implemented" in r.text


def test_approvals_correctly_empty_today(monkeypatch):
    _as(monkeypatch, COMMERCIAL_MANAGER)
    r = client().get("/app/approvals")
    assert "No quotes awaiting approval" in r.text
