# Spike: Cross-Currency Lane Repricing and Approval

**Status: policy-evaluation layer built + green.** The Cedar decision layer
([`policy-evaluation/`](policy-evaluation/README.md)) runs for real against an
isolated cedar-agent — all 4 scenarios + 3 failure injections pass. The mock
backends/frontends/agents (everything else in this document) are still described,
not built — see `../../build-plan.md` Phases 2–8.

## Decision being verified

That the cpm-eaop control-plane architecture — external Cedar PDP, authored actions,
projected schema, obligations resolved Python-side, a PEP enforcing them — can drive
a **real, event-triggered, multi-agent, human-in-the-loop business slice**, and that
**three distinct threshold types produce three distinct policy behaviors** (permit,
permit+obligation, forbid/deny-precedence) rather than one tangled rule.

## Hypothesis

One changing external fact (the FX rate) cascades through cost recalculation → route
re-ranking → a Cedar threshold → a forbid that beats a permit → mandatory human
approval → a durable state write-back — all expressible with the mirrored authz
artifacts in `../../authorization/` and observable as the decisions in
`../../scenarios/01-fx-flips-lane.yaml`.

## Interfaces implemented (when built)

| Interface | Role | Spec |
| --- | --- | --- |
| FX API | direct HTTP, deterministic, easy to mock | `../../src/mock-fx/` (built, live `/openapi.json`) |
| TMS / Rate / Commercial / Approval MCP | agent → systems of record | `../../interfaces/mcp/tools.yaml` |
| A2A | Lane → Commercial → Route Decision handoff | `../../interfaces/a2a/handoff.md` |
| Cedar PDP | decision point | copies cpm-eaop `cedar-agent` + `src/spike/model` |

## Mock services to build (specified, not coded)

```text
mock-fx/          FX rate by pair + effectiveAt; returns rate/observed_at/valid_until/rate_ref
mock-tms/         feasible lanes, transit, capacity for RFQ-1001
mock-rate/        carrier + contract rates in local currencies (CNY, EUR)
mock-commercial/  margin floor, previous quote, surcharges
mock-approval/    create/get human approval task; carries decision evidence
mock-agents/      lane-evaluation · commercial-normalization · route-decision
policy-evaluation/ copies the minimal cpm-eaop engine + policies to decide P·A·R·C
end-to-end/       runs scenario 01 through the mocks + PDP
```

## Deliberate simplifications

- Entra tenant simulated; agents are service principals with Keycloak client ids.
- Carrier/CRM/TMS/QMS are static fixtures, not real integrations.
- FX rates are fixture values (one "yesterday", one "today").
- Money is EUR cents; percents are integer tenths (Cedar has no decimal type).
- A2A messages are not durable in the first cut.
- The engine (`cedar-agent` + `src/spike/model`) is **copied** from cpm-eaop, not
  shared — this is a standalone GEAP spike.

## Test scenarios

- Primary: `../../scenarios/01-fx-flips-lane.yaml` (FX flips the ranking; D4b denies
  auto-submit; D6 human approval is the only path).
- Failure injection: stale FX → D1 deny · inactive principal → D7 deny · kill switch
  on the commercial agent → fail closed.
- Gating (mirror cpm-eaop `tests/test_model.py`): `_sidecar_up()` skip when
  cedar-agent is down; `mock_pdp` for unit tests vs a real `pdp` fixture for
  `test_int_*` integration tests.

## Evidence (to capture when run)

Per-step PDP decisions with `decision_id` + determining policy ids matching the
`then.authorization` block of the scenario; the resolved obligations; the written
quote version carrying the FX snapshot ref; the audit event stream.

## Result

**Decision supported** (policy-evaluation layer). All 4 scenarios + 3 failure
injections pass against a live, isolated cedar-agent (see
`policy-evaluation/README.md` for the run + the 3 real bugs it surfaced and fixed).
The mock backends/agents/frontends remain unbuilt — that verdict is still pending.

## Architecture consequence

_To record after the run_ (e.g. confirms deny-precedence + Python-side obligations
are sufficient to model the three threshold types; or surfaces a gap in entity-data
sync at request time — the known cpm-eaop `cedar-agent` constraint).

## Open questions

1. Entity-data sync — per-request `/v1/data` PUT of dynamic RFQ/Quote/RouteOption is
   the known cpm-eaop `cedar-agent` constraint; EntityProvider/cache or OPAL later.
2. Decimal handling — is tenths-of-a-percent + cents sufficient, or is a fixed-point
   convention needed across the money math?
3. Long-running human loop — how is the approval wait modeled (durable task vs poll)?
4. FX snapshot auditability — is a signed `rate_ref` required for the write-back?
