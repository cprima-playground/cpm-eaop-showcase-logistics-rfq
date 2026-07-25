"""POST/GET .../decisions: the real D19-candidate action -- approval_required
-> approved | rejected | revise, with a DecisionRecord kept alongside."""

from fastapi.testclient import TestClient

from conftest import TEST_API_KEY as API_KEY
from mock_qms.api import build_app


def client():
    return TestClient(build_app())


def _create_quote(c):
    return c.post(
        "/quotes", headers={"X-API-Key": API_KEY},
        json={"rfq_id": "RFQ-9001", "customer_id": "ACME", "currency": "EUR"},
    ).json()


def _to_approval_required(c, quote_id, version=1):
    c.put(
        f"/quotes/{quote_id}/versions/{version}/route-recommendation", headers={"X-API-Key": API_KEY},
        json={"recommendation_id": "REC-9001-v1", "selected_route_id": "SHA-HAM-MUC"},
    )
    c.put(
        f"/quotes/{quote_id}/versions/{version}/pricing-inputs", headers={"X-API-Key": API_KEY},
        json={
            "fx_rate_ref": "FX-20260724-CNY-EUR", "rate_refs": ["SHA-HAM-MUC"],
            "pricing_terms_ref": "PT-1", "margin_floor_ref": "standard",
        },
    )
    c.post(f"/quotes/{quote_id}/versions/{version}/price", headers={"X-API-Key": API_KEY})
    c.post(f"/quotes/{quote_id}/versions/{version}/submit-for-approval", headers={"X-API-Key": API_KEY})


def test_decide_before_approval_required_is_409():
    c = client()
    q = _create_quote(c)
    r = c.post(
        f"/quotes/{q['quote_id']}/versions/1/decisions", headers={"X-API-Key": API_KEY},
        json={"decision": "approved", "approver": "mona.commercial"},
    )
    assert r.status_code == 409


def test_approve_records_decision_and_transitions_status():
    c = client()
    q = _create_quote(c)
    _to_approval_required(c, q["quote_id"])

    r = c.post(
        f"/quotes/{q['quote_id']}/versions/1/decisions", headers={"X-API-Key": API_KEY},
        json={"decision": "approved", "approver": "mona.commercial", "reason": "margin acceptable"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

    history = c.get(f"/quotes/{q['quote_id']}/versions/1/decisions", headers={"X-API-Key": API_KEY}).json()
    assert len(history) == 1
    assert history[0]["decision"] == "approved"
    assert history[0]["approver"] == "mona.commercial"
    assert history[0]["reason"] == "margin acceptable"

    quote = c.get(f"/quotes/{q['quote_id']}", headers={"X-API-Key": API_KEY}).json()
    assert quote["latest_version_status"] == "approved"


def test_reject_and_revise_are_also_real():
    c = client()
    q1 = _create_quote(c)
    _to_approval_required(c, q1["quote_id"])
    r1 = c.post(
        f"/quotes/{q1['quote_id']}/versions/1/decisions", headers={"X-API-Key": API_KEY},
        json={"decision": "rejected", "approver": "mona.commercial"},
    )
    assert r1.json()["status"] == "rejected"

    q2 = c.post(
        "/quotes", headers={"X-API-Key": API_KEY},
        json={"rfq_id": "RFQ-9002", "customer_id": "ACME", "currency": "EUR"},
    ).json()
    _to_approval_required(c, q2["quote_id"])
    r2 = c.post(
        f"/quotes/{q2['quote_id']}/versions/1/decisions", headers={"X-API-Key": API_KEY},
        json={"decision": "revise", "approver": "mona.commercial"},
    )
    assert r2.json()["status"] == "revise"


def test_deciding_an_already_decided_version_is_409():
    c = client()
    q = _create_quote(c)
    _to_approval_required(c, q["quote_id"])
    c.post(
        f"/quotes/{q['quote_id']}/versions/1/decisions", headers={"X-API-Key": API_KEY},
        json={"decision": "approved", "approver": "mona.commercial"},
    )
    r = c.post(
        f"/quotes/{q['quote_id']}/versions/1/decisions", headers={"X-API-Key": API_KEY},
        json={"decision": "approved", "approver": "mona.commercial"},
    )
    assert r.status_code == 409
