"""Human-in-the-loop narrative (business/decisions.md's "Human-in-the-loop
= a status change in the quote system of record"): a priced quote must be
submitted for approval before a commercial manager's decision can move it
to a terminal state, and that decision -- approve or reject -- is durable
QuoteVersion status, not a side record. No Cedar gate governs
quote.submit-for-approval or the decision itself yet (see mock_qms/api.py's
own x-gap on POST .../decisions) -- this proves the real state machine
underneath where that gate will eventually attach, not the authorization
decision itself. Live, cross-service: TMS must confirm SHA-HAM-MUC is
executable before QMS will even let this quote reach `priced`."""


def _price_a_quote(qms_client, rfq_id: str) -> str:
    quote_id = qms_client.post(
        "/quotes", json={"rfq_id": rfq_id, "customer_id": "ACME", "currency": "EUR"},
    ).json()["quote_id"]
    qms_client.put(
        f"/quotes/{quote_id}/versions/1/route-recommendation",
        json={"recommendation_id": f"REC-{rfq_id}", "selected_route_id": "SHA-HAM-MUC"},
    )
    qms_client.put(
        f"/quotes/{quote_id}/versions/1/pricing-inputs",
        json={
            "fx_rate_ref": "FX-20260724-CNY-EUR", "rate_refs": ["SHA-HAM-MUC"],
            "pricing_terms_ref": "PT-1", "margin_floor_ref": "standard",
        },
    )
    r = qms_client.post(f"/quotes/{quote_id}/versions/1/price")
    assert r.status_code == 200
    assert r.json()["status"] == "priced"
    return quote_id


def test_priced_quote_requires_submission_before_a_decision_can_be_recorded(qms_client, tms_client):
    tms_client.post("/admin/reset")
    try:
        quote_id = _price_a_quote(qms_client, "RFQ-APPROVAL-GATE")

        # a decision can't be recorded on a version that hasn't been
        # submitted -- approval_required is a real precondition, not a label.
        r = qms_client.post(
            f"/quotes/{quote_id}/versions/1/decisions",
            json={"decision": "approved", "approver": "mona.commercial", "reason": "looks fine"},
        )
        assert r.status_code == 409

        r = qms_client.post(f"/quotes/{quote_id}/versions/1/submit-for-approval")
        assert r.status_code == 200
        assert r.json()["status"] == "approval_required"

        # now visible to whoever is triaging pending approvals
        pending = qms_client.get("/quotes", params={"status": "approval_required"}).json()
        assert any(q["quote_id"] == quote_id for q in pending)
    finally:
        tms_client.post("/admin/reset")


def test_commercial_manager_approves_a_submitted_quote(qms_client, tms_client):
    tms_client.post("/admin/reset")
    try:
        quote_id = _price_a_quote(qms_client, "RFQ-APPROVAL-APPROVE")
        qms_client.post(f"/quotes/{quote_id}/versions/1/submit-for-approval")

        r = qms_client.post(
            f"/quotes/{quote_id}/versions/1/decisions",
            json={"decision": "approved", "approver": "mona.commercial", "reason": "within standard margin"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

        # the decision itself is durable, supporting evidence -- not the
        # authoritative signal (that's QuoteVersion.status, per
        # business/decisions.md) -- but it must still be retrievable.
        decisions = qms_client.get(f"/quotes/{quote_id}/versions/1/decisions").json()
        assert len(decisions) == 1
        assert decisions[0]["decision"] == "approved"
        assert decisions[0]["approver"] == "mona.commercial"

        quote = qms_client.get(f"/quotes/{quote_id}").json()
        assert quote["latest_version_status"] == "approved"

        # re-deciding an already-decided version is rejected -- approved is terminal here.
        r = qms_client.post(
            f"/quotes/{quote_id}/versions/1/decisions",
            json={"decision": "rejected", "approver": "mona.commercial", "reason": "changed my mind"},
        )
        assert r.status_code == 409
    finally:
        tms_client.post("/admin/reset")


def test_commercial_manager_rejects_a_submitted_quote_with_a_reason(qms_client, tms_client):
    tms_client.post("/admin/reset")
    try:
        quote_id = _price_a_quote(qms_client, "RFQ-APPROVAL-REJECT")
        qms_client.post(f"/quotes/{quote_id}/versions/1/submit-for-approval")

        r = qms_client.post(
            f"/quotes/{quote_id}/versions/1/decisions",
            json={"decision": "rejected", "approver": "mona.commercial", "reason": "margin too thin for this lane"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

        decisions = qms_client.get(f"/quotes/{quote_id}/versions/1/decisions").json()
        assert decisions[0]["decision"] == "rejected"
        assert decisions[0]["reason"] == "margin too thin for this lane"

        # rejection is a real terminal outcome, visible on the quote itself --
        # not merely on the decision record.
        quote = qms_client.get(f"/quotes/{quote_id}").json()
        assert quote["latest_version_status"] == "rejected"
    finally:
        tms_client.post("/admin/reset")
