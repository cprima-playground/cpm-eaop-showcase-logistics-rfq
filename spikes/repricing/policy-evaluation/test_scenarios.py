"""Prove the acceptance criteria for scenarios 01-04 + failure injections against
a live, isolated cedar-agent. Each test's docstring states the acceptance criterion
it verifies (see the goal table / spikes/repricing/README.md)."""

from __future__ import annotations

import httpx
import pytest

import entities
import kill_switch
import scenario_runner as sr

CEDAR_URL = "http://localhost:8280"


def _by_action(results: list[dict]) -> dict[str, dict]:
    return {r["action"]: r for r in results}


# --- scenario 01: FX flips lane ------------------------------------------------

def test_01_fx_flips_lane():
    """FX alone flips ranking; D4b forbid denies auto-submit (deny-precedence);
    D6 human approval is the only path + succeeds within limit."""
    results = _by_action(sr.run_scenario("01-fx-flips-lane"))

    assert results["fx-rate.read"]["effect"] == "allow"
    assert results["fx-rate.read"]["determining"] == ["commercial-may-read-fresh-fx"]

    assert results["route-cost.normalize"]["effect"] == "allow"

    # cost_variance_pct_x10=93 (9.3%) also exceeds D8's 8% threshold -> obligations MERGE
    rec = results["route.recommend"]
    assert rec["effect"] == "allow"
    assert rec["determining"] == sorted(["recommend-high-cost-variance", "recommend-noncontracted-lane"])
    assert rec["obligations"] == sorted(["oblig-cost-variance-review", "oblig-lane-deviation"])

    # D4b forbid wins (deny-precedence) -- the agent cannot auto-submit
    assert results["quote.submit-for-approval"]["effect"] == "deny"
    assert results["quote.submit-for-approval"]["determining"] == ["forbid-auto-replace-on-fx"]

    # D6: human approval is the only path forward, and succeeds within limit
    assert results["route-deviation.approve"]["effect"] == "allow"
    assert results["route-deviation.approve"]["determining"] == ["manager-may-approve-within-limit"]


# --- scenario 02: route unavailable --------------------------------------------

def test_02_route_unavailable():
    """Same chain to human approval with MERGED obligations (lane+transit);
    NO forbid -- architecture is event-source-agnostic."""
    results = _by_action(sr.run_scenario("02-route-unavailable"))

    assert results["capacity.check"]["effect"] == "allow"

    assert results["route-cost.normalize"]["effect"] == "allow"

    rec = results["route.recommend"]
    assert rec["effect"] == "allow"
    assert rec["determining"] == sorted(["recommend-noncontracted-lane", "recommend-slower-transit"])
    assert rec["obligations"] == sorted(["oblig-lane-deviation", "oblig-transit-review"])

    # no forbid: FX quiet, margin above floor
    assert results["quote.submit-for-approval"]["effect"] == "allow"

    assert results["route-deviation.approve"]["effect"] == "allow"
    assert results["route-deviation.approve"]["determining"] == ["manager-may-approve-within-limit"]


# --- scenario 03: approval loop (long-running HITL) ----------------------------

def test_03_approval_loop():
    """A `revise` status transition (not a workflow callback) resumes the
    process; 2nd pass over the SAME agents/policies reaches a fresh approval
    (contracted lane this time -> no obligation); ends on `approved`. No agent
    holds authoritative state across the wait -- the runner re-derives every
    decision from the scenario's given/when, nothing carried in-process."""
    doc = sr.load_scenario("03-approval-loop")

    # the status trail itself is the resumption mechanism, not a callback
    assert doc["then"]["status_trail"] == ["approval_required", "revise", "approval_required", "approved"]

    results = _by_action(sr.run_scenario("03-approval-loop"))

    assert results["lane.evaluate"]["effect"] == "allow"
    assert results["route-cost.normalize"]["effect"] == "allow"

    # D3a: contracted lane this time -> allow, NO obligation
    rec = results["route.recommend"]
    assert rec["effect"] == "allow"
    assert rec["determining"] == ["recommend-contracted-lane"]
    assert rec["obligations"] == []

    assert results["route-deviation.approve"]["effect"] == "allow"
    assert results["route-deviation.approve"]["determining"] == ["manager-may-approve-within-limit"]


# --- scenario 04: combined route + FX shock (flagship) -------------------------

def test_04_combined_route_fx_shock():
    """Reroute AND FX repricing from one event; forbid denies auto-submit;
    obligations merge (lane+transit+FX-notify); human Quote.status transition
    is the only path, succeeds within limit."""
    results = _by_action(sr.run_scenario("04-combined-route-fx-shock"))

    assert results["fx-rate.read"]["effect"] == "allow"
    assert results["route-cost.normalize"]["effect"] == "allow"

    var = results["quote-variance.evaluate"]
    assert var["effect"] == "allow"
    assert var["determining"] == ["fx-permit-recalc"]
    assert var["obligations"] == ["oblig-notify-pricing-manager"]

    rec = results["route.recommend"]
    assert rec["effect"] == "allow"
    assert rec["determining"] == sorted(["recommend-noncontracted-lane", "recommend-slower-transit"])
    assert rec["obligations"] == sorted(["oblig-lane-deviation", "oblig-transit-review"])

    # forbid wins (deny-precedence) despite multiple permits existing for other actions
    assert results["quote.submit-for-approval"]["effect"] == "deny"
    assert results["quote.submit-for-approval"]["determining"] == ["forbid-auto-replace-on-fx"]

    assert results["route-deviation.approve"]["effect"] == "allow"
    assert results["route-deviation.approve"]["determining"] == ["manager-may-approve-within-limit"]


# --- failure injections ---------------------------------------------------------

def test_stale_fx_denies():
    """stale FX -> D1 deny (no policy permits a read outside the freshness window;
    default-deny, no forbid needed)."""
    result = sr.run_step({
        "action": "fx-rate.read",
        "principal": "commercial-normalization-agent",
        "resource": "ExchangeRate::CNY-EUR",
        "context": {"fx_age_seconds": 3600, "quote_currency": "EUR"},  # 1h old, > 900s window
    })
    assert result["effect"] == "deny"
    assert result["determining"] == []  # no policy matches -> default-deny


def test_inactive_principal_denies():
    """inactive principal -> D7 deny (forbid-inactive, cross-cutting)."""
    # load the static baseline + one inactive test-only agent (never used by any
    # scenario), so this test can't corrupt state for the scenario tests.
    extra = entities.agent_entity("test-inactive-agent", active=False)
    httpx.put(f"{CEDAR_URL}/v1/data", json=entities.static_entities() + [extra], timeout=10.0).raise_for_status()
    try:
        body = {
            "principal": entities.ref("AgentPrincipal", "test-inactive-agent"),
            "action": entities.action_ref("fx-rate.read"),
            "resource": entities.ref("ExchangeRate", "CNY-EUR"),
            "context": {"fx_age_seconds": 100, "quote_currency": "EUR"},  # otherwise-fresh
        }
        r = httpx.post(f"{CEDAR_URL}/v1/is_authorized", json=body, timeout=10.0)
        r.raise_for_status()
        data = r.json()
        assert data["decision"] == "Deny"
        assert data["diagnostics"]["reason"] == ["forbid-inactive"]
    finally:
        httpx.put(f"{CEDAR_URL}/v1/data", json=entities.static_entities(), timeout=10.0).raise_for_status()


def test_kill_switch_fails_closed():
    """kill-switch -> fail closed. The PEP pre-check short-circuits to deny
    BEFORE Cedar is ever called (governance-policies.md: checked before executing
    an MCP tool / accepting a task)."""
    kill_switch.disable_agent("commercial-normalization-agent")
    result = sr.run_step({
        "action": "fx-rate.read",
        "principal": "commercial-normalization-agent",
        "resource": "ExchangeRate::CNY-EUR",
        "context": {"fx_age_seconds": 100, "quote_currency": "EUR"},  # would otherwise allow
    })
    assert result["effect"] == "deny"
    assert result["reason"] == "kill-switch"
