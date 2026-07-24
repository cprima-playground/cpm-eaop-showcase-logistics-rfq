# TODO — showcase gaps

Design-stage gaps only (missing design docs/decisions). Building/running/demoing is
planned separately in **`build-plan.md`** (phased). Code / running mocks / Terraform
are known `TARGET` (see `spikes/`, `deploy/`). Ordered by priority.

Decided since first draft: theming (**ADR-007** + `themes/` + `systems/theming.md`);
tech stack (**ADR-006**, one open item — agent identity); reference data + scenario
packs + determinism (`RUNNING.md`).

## Must-have (package integrity)

- [~] **ADR log** — `decisions/` started (index + **ADR-006 tech-stack** proposed +
      **ADR-007 theming** accepted).
      Still to write: the seed's five domain ADRs — ADR-001 agentic-rfq-scope ·
      ADR-002 SoR-boundaries · ADR-003 agent/tool-boundaries · ADR-004 authorization-model ·
      ADR-005 human-approval-boundaries. (`business/decisions.md` is *authz* decisions, not ADRs.)
- [ ] **Threat model** — `threat-model.md`. Agentic-specific: forged agent identity ·
      unauthorized delegation · prompt-driven tool misuse · stale quote accepted ·
      bypass of human approval · kill-switch not honored · cross-customer disclosure.
- [ ] **NFRs** — `non-functional-requirements.yaml`. default-deny · delegation
      max-depth · auditability (every decision has an id) · latency budget.
- [ ] **Audit-event vocabulary** — `audit-events.yaml`. Currently only inline in
      `business/process.md`; needs a stable file to assert against.
- [ ] **Complete identity:**
  - [ ] `identity/entra-objects.yaml` (referenced in the reuse map, does not exist)
  - [ ] `identity/groups.yaml` (full directory; actors only sketch groups inline)
  - [ ] `identity/delegation-model.md` (A2A **signed delegation-chain**)
  - [ ] `identity/terraform/` (TARGET stub — client-secret pattern per `infra/entra`)
- [x] **Entity / request assembly** — **built**, `rfq_common.pdp` (`ref`/`uid`/
      `action_ref`, path/namespace-parameterized). Proven against 5 real decisions
      through the isolated cedar-agent. Still open: wiring dynamic per-request
      resource attributes if a future policy ever needs one (none do today — every
      condition reads only `context.*`/`principal.*`).
- [ ] **Grants / hot-path decision** — does the repricing slice use short-lived grants
      (decide-once-redeem-locally, per cpm-eaop) or per-call decisions? `grant.issue`
      exists in governance actions but no grant flow is documented.
- [x] **`rfq_common` library** — **built**, `src/rfq_common/`, 33 tests green (build-plan
      Phase 1, done). Pydantic entity models · jsonl loader · JWT/JWKS verify · PDP
      client + schema generator + policy bundle · theme model/renderer · clock/seed ·
      base FastAPI/Typer apps.
- [ ] **Observability design** — how a `correlation_id`/`run_id` propagates
      agent→PEP→PDP→SoR; the audit sink; what each hop logs.
- [ ] **Scenario-runner interface** — the concrete CLI surface (`rfq scenario apply
      <pack>`) implementing `RUNNING.md` behavior (reset · apply · pin clock · re-PUT PDP · run_id).
- [ ] **Kill-switch runtime design** — where switch state lives + the check before each
      governed edge (accept A2A · run tool · issue grant · commit side effect).

## Should-have

- [ ] `authorization/policy-test-cases.yaml` — per-decision **permit / deny / edge**
      fixtures (runbook step 7; scenarios cover happy path only).
- [ ] `risks.md` — stale policy context · agent replay · duplicate booking ·
      kill-switch propagation delay · identity↔agent inventory drift · non-deterministic
      model output.
- [ ] `assumptions.md` — Entra simulated · static rates · deterministic calc · no real
      carrier integration.
- [ ] `interfaces/cli/commands.yaml` — the CLI (spec'd in `systems/mock-architecture.md`,
      no command list yet).
- [ ] `interfaces/a2a/agent-cards/*.json` — per-agent cards (handoff.md sketches one).
- [ ] `interfaces/api/{rfq,pricing,booking}.openapi.yaml` — TARGET stubs.
- [ ] `business/glossary.md` — RFQ · lane · Incoterm · margin floor · freshness window ·
      baseline lane.

## Nice-to-have

- [ ] `business/process.bpmn` — authoritative process viz (vs the `.mmd` simplified view).
- [ ] Per-area `README.md` index files.

## Structural holes (call out explicitly)

- [x] **Second authorization boundary** (agent→tool, then **tool→API**) — **descoped**
      (ADR-008 Related): the showcase governs agent→tool via Cedar; tool→API is
      implementation, not modeled. *This is a showcase, not the implementation.*
- [ ] **Business-event ingestion** — how a business event (FX change / route
      unavailable) *wakes* the process. Partly addressed by scenario packs + triggers;
      the *ingestion path* (event → discover impacted quotes) is still undocumented.
- [ ] **Deterministic-run mechanism** — `RUNNING.md` specifies it (admin reset +
      `scenario apply` + pinned `NOW` + seed + PDP re-PUT + `run_id`); not built. The
      clock-pinning (`NOW` injection) is the load-bearing part — without it D1/D2 flip
      on wall-clock.

## Suggested sequence

ADRs → threat-model + NFRs → identity completion + entity-assembly → grants decision.
Those make the package internally complete and honest; the rest is breadth.
