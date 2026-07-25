"""Real (partial) pricing pipeline: route-recommendation/pricing-inputs
composition, POST .../price (real total_cost via mock-rate+mock-fx stubs,
honest not_evaluated for R1/R3/R4/R5), POST .../submit-for-approval."""

from fastapi.testclient import TestClient

from conftest import TEST_API_KEY as API_KEY
from conftest import StubFxClient
from mock_qms.api import build_app


def client():
    return TestClient(build_app())


def _create_quote(c):
    return c.post(
        "/quotes", headers={"X-API-Key": API_KEY},
        json={"rfq_id": "RFQ-9001", "customer_id": "ACME", "currency": "EUR"},
    ).json()


def _compose(c, quote_id, version, margin_floor_ref="standard"):
    c.put(
        f"/quotes/{quote_id}/versions/{version}/route-recommendation", headers={"X-API-Key": API_KEY},
        json={"recommendation_id": "REC-9001-v1", "selected_route_id": "SHA-HAM-MUC"},
    )
    c.put(
        f"/quotes/{quote_id}/versions/{version}/pricing-inputs", headers={"X-API-Key": API_KEY},
        json={
            "fx_rate_ref": "FX-20260724-CNY-EUR", "rate_refs": ["SHA-HAM-MUC"],
            "pricing_terms_ref": "PT-1", "margin_floor_ref": margin_floor_ref,
        },
    )


def test_route_recommendation_and_pricing_inputs_compose_real_fields():
    c = client()
    q = _create_quote(c)
    r = c.put(
        f"/quotes/{q['quote_id']}/versions/1/route-recommendation", headers={"X-API-Key": API_KEY},
        json={"recommendation_id": "REC-1", "selected_route_id": "SHA-HAM-MUC"},
    )
    assert r.status_code == 200
    assert r.json()["recommendation_id"] == "REC-1"
    assert r.json()["selected_route_id"] == "SHA-HAM-MUC"

    r2 = c.put(
        f"/quotes/{q['quote_id']}/versions/1/pricing-inputs", headers={"X-API-Key": API_KEY},
        json={"fx_rate_ref": "FX-X", "rate_refs": ["SHA-HAM-MUC"], "pricing_terms_ref": "PT-1", "margin_floor_ref": "MF-1"},
    )
    assert r2.status_code == 200
    assert r2.json()["rate_refs"] == ["SHA-HAM-MUC"]


def test_price_without_composition_is_400():
    c = client()
    q = _create_quote(c)
    r = c.post(f"/quotes/{q['quote_id']}/versions/1/price", headers={"X-API-Key": API_KEY})
    assert r.status_code == 400


def test_price_computes_real_total_cost_and_honest_rule_results():
    c = client()
    q = _create_quote(c)
    _compose(c, q["quote_id"], 1)

    r = c.post(f"/quotes/{q['quote_id']}/versions/1/price", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "priced"

    # 42000 + 5100 = 47100 CNY-cents = 471.00 CNY -> * 0.13 (stub fx rate) = 61.23 EUR = 6123 EUR-cents
    assert body["total_cost_eur_cents"] == 6123
    assert body["fx_rate_snapshot"] == 0.13

    results = {rr["rule_id"]: rr for rr in body["pricing_rule_results"]}
    assert results["R2"]["result"] == "not_evaluated"  # no prior priced version yet
    for rule_id in ("R3", "R4", "R5"):
        assert results[rule_id]["result"] == "not_evaluated"
        assert "baseline" in results[rule_id]["reason"]

    # R1 is real now -- via the versioned, explicitly synthetic demo policy
    # (not fabricated silently: pricing_policy_ref names exactly which one).
    # cost 6123 -> target 18% (standard profile, FX not over threshold) ->
    # 6123/0.82 = 7467.07 -> ceiling 7468 -> commercial-rounded up to 7500 (€5 band)
    assert body["pricing_policy_ref"] == "demo-cost-plus-margin-v1"
    assert body["proposed_sell_price_eur_cents"] == 7500
    assert body["margin_pct_x10"] == 184
    assert results["R1"]["result"] == "within_threshold"
    assert "demo policy" in results["R1"]["reason"]
    assert "standard" in results["R1"]["reason"]


def test_price_governed_by_margin_floor_ref_profile():
    """Same cost, different margin_floor_ref -> different sell price -- the
    real governance surface, not a hardcoded number."""
    c = client()
    q_standard = _create_quote(c)
    _compose(c, q_standard["quote_id"], 1, margin_floor_ref="standard")
    standard = c.post(f"/quotes/{q_standard['quote_id']}/versions/1/price", headers={"X-API-Key": API_KEY}).json()

    q_strategic = c.post(
        "/quotes", headers={"X-API-Key": API_KEY},
        json={"rfq_id": "RFQ-9002", "customer_id": "ACME", "currency": "EUR"},
    ).json()
    _compose(c, q_strategic["quote_id"], 1, margin_floor_ref="strategic-account")
    strategic = c.post(f"/quotes/{q_strategic['quote_id']}/versions/1/price", headers={"X-API-Key": API_KEY}).json()

    # strategic-account's lower base margin (12% vs 18%) -> a lower sell price for the same cost
    assert strategic["proposed_sell_price_eur_cents"] < standard["proposed_sell_price_eur_cents"]
    standard_r1 = {rr["rule_id"]: rr for rr in standard["pricing_rule_results"]}["R1"]
    strategic_r1 = {rr["rule_id"]: rr for rr in strategic["pricing_rule_results"]}["R1"]
    assert standard_r1["threshold_pct_x10"] == 180
    assert strategic_r1["threshold_pct_x10"] == 120


def test_unrecognized_margin_floor_ref_falls_back_to_standard_profile():
    c = client()
    q = _create_quote(c)
    _compose(c, q["quote_id"], 1, margin_floor_ref="MF-TYPO-DOES-NOT-EXIST")
    r = c.post(f"/quotes/{q['quote_id']}/versions/1/price", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    r1 = {rr["rule_id"]: rr for rr in r.json()["pricing_rule_results"]}["R1"]
    assert r1["threshold_pct_x10"] == 180  # standard profile's base margin, not an error


def test_margin_floor_endpoint_is_real():
    c = client()
    r = c.get("/margin-floors/strategic-account", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert r.json()["base_margin_pct_x10"] == 120

    r404 = c.get("/margin-floors/does-not-exist", headers={"X-API-Key": API_KEY})
    assert r404.status_code == 404


def test_price_already_priced_is_409():
    c = client()
    q = _create_quote(c)
    _compose(c, q["quote_id"], 1)
    c.post(f"/quotes/{q['quote_id']}/versions/1/price", headers={"X-API-Key": API_KEY})
    r = c.post(f"/quotes/{q['quote_id']}/versions/1/price", headers={"X-API-Key": API_KEY})
    assert r.status_code == 409


def test_submit_for_approval_requires_priced():
    c = client()
    q = _create_quote(c)
    r = c.post(f"/quotes/{q['quote_id']}/versions/1/submit-for-approval", headers={"X-API-Key": API_KEY})
    assert r.status_code == 409


def test_full_pipeline_reaches_approval_required_for_real():
    c = client()
    q = _create_quote(c)
    _compose(c, q["quote_id"], 1)
    c.post(f"/quotes/{q['quote_id']}/versions/1/price", headers={"X-API-Key": API_KEY})
    r = c.post(f"/quotes/{q['quote_id']}/versions/1/submit-for-approval", headers={"X-API-Key": API_KEY})
    assert r.status_code == 200
    assert r.json()["status"] == "approval_required"

    # now a real row in search(status=approval_required) and GET /quotes/{id}
    search = c.get("/quotes", headers={"X-API-Key": API_KEY}, params={"status": "approval_required"}).json()
    assert any(x["quote_id"] == q["quote_id"] for x in search)

    quote = c.get(f"/quotes/{q['quote_id']}", headers={"X-API-Key": API_KEY}).json()
    assert quote["latest_version_status"] == "approval_required"


def test_r2_becomes_real_on_a_second_priced_version_fx_breakout_scenario():
    """The planned FX-breakout scenario: reprice a superseded version after
    the rate has moved -- R2 should now be a real within/over_threshold
    result, not not_evaluated."""
    c = client()
    q = _create_quote(c)
    _compose(c, q["quote_id"], 1)
    v1 = c.post(f"/quotes/{q['quote_id']}/versions/1/price", headers={"X-API-Key": API_KEY}).json()
    assert v1["fx_rate_snapshot"] == 0.13

    c.post(
        f"/quotes/{q['quote_id']}/versions", headers={"X-API-Key": API_KEY, "Idempotency-Key": "k1"},
        json={"prior_version": 1, "expected_latest_version": 1, "copy_from_prior": True},
    )
    # simulate the FX rate moving (breakout) before the new draft is repriced
    StubFxClient.rate = 0.20

    v2 = c.post(f"/quotes/{q['quote_id']}/versions/2/price", headers={"X-API-Key": API_KEY}).json()
    r2 = {rr["rule_id"]: rr for rr in v2["pricing_rule_results"]}["R2"]
    assert r2["result"] == "over_threshold"  # (0.20-0.13)/0.13*1000 = 538 >> 20
    assert r2["actual_pct_x10"] == 538
