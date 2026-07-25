"""Commercial-Preconditions narrative (ADR-011), per business/decisions.md
D3b/D9: a contracted route blocked by TMS gets pricing rejected; a tagged
alternative recommendation recovers it. Live, cross-service -- proves the
actual gap this session's TMS-wiring work exists to close, not just a
stub's behavior. One function, not numbered test methods: pytest's
definition-order execution is an implementation detail, not a business
guarantee, and this narrative's sequential dependency should be explicit
in plain code instead."""


def test_hamburg_closure_then_reroute_recovers(qms_client, tms_client):
    tms_client.post("/admin/reset")
    try:
        quote_id = qms_client.post(
            "/quotes", json={"rfq_id": "RFQ-HAMBURG-CLOSURE", "customer_id": "ACME", "currency": "EUR"},
        ).json()["quote_id"]

        # 1. baseline: the contracted route prices normally.
        qms_client.put(
            f"/quotes/{quote_id}/versions/1/route-recommendation",
            json={"recommendation_id": "REC-HH-1", "selected_route_id": "SHA-HAM-MUC"},
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

        # 2. Hamburg closes -- TMS is the sole source of this truth.
        closure = tms_client.patch(
            "/routes/SHA-HAM-MUC/availability",
            json={"status": "unavailable", "reason": "port congestion"},
        )
        assert closure.status_code == 200

        # 3. superseding to v2 on the SAME route is rejected -- QMS honors
        # TMS's current truth, not the stale state it saw at v1.
        qms_client.post(
            f"/quotes/{quote_id}/versions", headers={"Idempotency-Key": "hamburg-closure-v2"},
            json={"prior_version": 1, "expected_latest_version": 1, "copy_from_prior": True},
        )
        r = qms_client.post(f"/quotes/{quote_id}/versions/2/price")
        assert r.status_code == 409
        assert "commercial precondition" in r.text
        assert "route" in r.text and "not established" in r.text
        assert "unavailable" in r.text

        # 4. a tagged alternative route recovers pricing.
        qms_client.put(
            f"/quotes/{quote_id}/versions/2/route-recommendation",
            json={"recommendation_id": "REC-HH-2", "selected_route_id": "SHA-RTM-MUC"},
        )
        qms_client.put(
            f"/quotes/{quote_id}/versions/2/pricing-inputs",
            json={
                "fx_rate_ref": "FX-20260724-EUR-EUR", "rate_refs": ["SHA-RTM-MUC"],
                "pricing_terms_ref": "PT-1", "margin_floor_ref": "standard",
            },
        )
        r = qms_client.post(f"/quotes/{quote_id}/versions/2/price")
        assert r.status_code == 200
    finally:
        tms_client.post("/admin/reset")
