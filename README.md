# Logistics RFQ — Agentic Showcase

A self-contained **architecture-decision package** for an agentic slice of the
logistics RFQ process. It proves one chain end-to-end:

```text
business event → agent discovers impacted quotes → agents enrich business state
→ policy evaluates business consequences → human decision (if required)
→ systems of record updated
```

The featured first spike is **Cross-Currency Lane Repricing and Approval** (business
title: *RFQ Route Cost Normalization and Exception Approval*) — the process wakes
because the *business world changed* (an FX rate moved, a lane became unavailable),
not because a workflow reached a step. See
[`spikes/repricing/`](spikes/repricing/README.md).

Two triggers, one architecture: an **FX change** (financial) and a **route
becoming unavailable** (operational) drive the *same* agents, policies, systems of
record, MCP tools, and A2A edges — see scenarios 01 and 02.

> **Status: design/decision package.** This showcase is standalone in GEAP; it
> **copies** the cpm-eaop control-plane conventions but does not share its code. The
> policy engine (`cedar-agent` + `src/spike/model`) lives in cpm-eaop; anything that
> must *run* here is described under `spikes/` as a mock, not implemented in this pass.

## Scope

- **In:** the repricing subprocess — event trigger, three agents, FX normalization,
  threshold policy, human-in-the-loop approval, durable state write-back.
- **Out (this pass):** RFQ intake, booking execution, real carrier/CRM/TMS
  integration, running code.

## The decision-first chain (how the areas connect)

```text
business/process.md      business event + happy/alt/exception paths
        ↓
business/actions.yaml    authored domain actions (Cedar shape)
        ↓
identity/actors.yaml     who acts (agents + human), via groups
        ↓
systems/*.yaml + data-provenance   authoritative fact sources (fail=deny)
        ↓
interfaces/ (mcp · api · a2a)      how facts are fetched / tasks handed off
        ↓
agents/catalog.yaml      which agent owns which action
        ↓
authorization/policies.cedar       may P do A on R under C?  (+ obligations)
        ↓
scenarios/01-fx-flips-lane.*       the exercised decision, given/when/then
        ↓
spikes/repricing/        the spike that would verify it (mocks)
```

## Reuse map — every artifact mirrors a proven cpm-eaop source

The authorization + identity artifacts here **copy** cpm-eaop shapes so the two
stay consistent. `TARGET` = design intent that does not yet exist in cpm-eaop.

| This showcase | Mirrors (cpm-eaop) | Notes |
| --- | --- | --- |
| `business/actions.yaml` | `data/policies/actions.yaml` | dotted names; `principals`/`resources`/`context` typing. Authored, never generated. |
| `authorization/authz-projection.yaml` | `data/policies/authz-projection.yaml` | coupling firewall; only `member_of`→`Group` is a parent; everything else a typed attribute; `namespace: Agentic`. |
| `authorization/agentic.cedarschema` | `data/policies/agentic.cedarschema` | **GENERATED** from projection+actions — not authored here (see note in file). |
| `authorization/policies.cedar` | `data/policies/policies.cedar` | `@id/@version/@owner/@description` + `@obligations("csv")`; `forbid`>`permit`; conditions read resolved attrs; uids `Agentic::Type::"id"`. |
| `authorization/obligations.yaml` | `data/policies/obligations.yaml` | `version:` + id→**flat** payload; Cedar never sees obligations. |
| `business/decisions.md` | `docs/policies/decisions.md` | table `# \| Question \| action \| principal \| resource \| context \| status \| policy id(s)`; `proposed→modeled→enforced`. |
| method | `docs/policies/domain-to-cedar-runbook.md` | decision-question first, Cedar last, never hand-edit the schema. |
| `agents/catalog.yaml` | `data/agents/hello-agent-*.yaml` | `caller_identity.keycloak_client` is load-bearing (drives `kind=agent`). |
| `identity/actors.yaml` | `data/identity/{groups,users,group_memberships}` | department/BU from group path→cost_center, not inline. |
| `identity/claims-contract.md` | `src/spike/model/identity.py` | claim keys: scope/scp · roles · groups→member_of · tid→trust_domain · active. |
| Entra adapter note | `src/spike/entra/principal.py` | `normalize_claims` layer (scp→scope, app-only, MSA tenant). |
| `identity/terraform/` `TARGET` | `infra/entra/main.tf` | client-secret pattern + real fixes. WIF federated creds + YAML→tfvars generator = `TARGET`. |
| `interfaces/a2a/` | `src/spike/a2a/hello_a2a/agent-card.json` | a2a-sdk 1.1 card shape. |
| `interfaces/mcp/`, `interfaces/api/` `TARGET` | — none in cpm-eaop — | no MCP server / no committed OpenAPI exist; green-field. |
| `scenarios/*` + spike gating | `tests/test_model.py`, `tests/spike/fixtures/entra/` | `_sidecar_up()` skip-gate, `mock_pdp` vs `pdp`, `test_int_*`; frozen fixtures, patterned GUIDs. |

## Status

| Area | Design | Mock | Spike | Verified |
| --- | :--: | :--: | :--: | :--: |
| Business process (repricing) | ✓ | — | — | — |
| Domain actions + decisions (D1–D9, all 7 thresholds) | ✓ | — | — | — |
| Cedar authorization | ✓ | — | — | — |
| Systems of record + provenance | ✓ | — | — | — |
| Mock system architecture (capability matrix + enterprise frontend) | ✓ | — | — | — |
| Tech stack (ADR-006) | ✓ proposed | — | — | — |
| Deploy → GCP mapping + container strategy (plan) | ✓ `TARGET` | — | — | — |
| Identity (actors/groups) | ✓ | — | — | — |
| Agents (3) | ✓ | — | — | — |
| FX API | ✓ `TARGET` | — | — | — |
| MCP servers/tools | ✓ `TARGET` | — | — | — |
| A2A handoff | ✓ | — | — | — |
| Reference data (real UN/LOCODE + synthetic ops) | ✓ | — | — | — |
| Scenario 01 (FX flips lane) | ✓ | — | — | — |
| Scenario 02 (route unavailable) | ✓ | — | — | — |
| Scenario 03 (approval loop / HITL) | ✓ | — | — | — |
| Scenario 04 (combined route + FX shock — flagship) | ✓ | — | — | — |
| Scenario packs (5, reproducible) | ✓ | — | — | — |
| Fixtures (given-state) | ✓ | — | — | — |
| Determinism / running (RUNNING.md) | ✓ | — | — | — |
| API contracts (OpenAPI 3.1 per API) | ✓ | — | — | — |
| Theming (ADR-007 · passable colorscheme) | ✓ | — | — | — |
| Build plan (phased) | ✓ | — | — | — |
| **Phase 1 — `rfq_common` foundation** | ✓ | — | ✓ **49 tests green** | ✓ |
| **Policy-evaluation spike (scenarios 01–04 + failures)** | ✓ | — | ✓ **7 tests green** | ✓ |
| **Phase 2 — mock-fx (first mock system, now consumes masterdata via API)** | ✓ | ✓ | ✓ **37 tests, verified live** | ✓ |
| **Phase 2 — mock-masterdata (ADR-010, 9 domains)** | ✓ | ✓ | ✓ **24 tests, verified live** | ✓ |
| Environments (dev·test·prod) + agent identity + persistence | ✓ decided | — | — | — |
| Credential inventory + management (ADR-009: Vault-dev/Secret Manager) | ✓ decided | ✓ **live** | ✓ | ✓ |

## Layout

```text
RfQ/
├── README.md                  ← you are here
├── RUNNING.md    deterministic demo runs (pin clock · seed · idempotent apply)
├── build-plan.md  phased build → run → demo (0 decide … 8 demo+CI)
├── TODO.md       design-stage gaps
├── KNOWN-ISSUES.md  bugs/limitations in already-built code (distinct from TODO/build-plan)
├── decisions/    10 ADRs, all accepted (001–005 domain · 006 stack · 007 theming · 008 agent runtime · 009 credentials · 010 masterdata)
├── src/rfq_common/  ★ REAL CODE — the Phase 1 foundation (46 tests green, see below)
├── src/mock-fx/     ★ REAL CODE — first Phase 2 system, verified LIVE (37 tests, consumes masterdata via API)
├── src/mock-masterdata/ ★ REAL CODE — masterdata source (ADR-010), verified LIVE (24 tests)
├── business/     process · actions · decisions · domain-model · domain-reference
├── systems/      systems-of-record · data-provenance · mock-architecture · reference-data · theming
│   └── crm/ tms/ rate/ cpq/ fx/ workflow/   ← per system (openapi.yaml · fixtures · mock spec)
│                 tms/fixtures: locations (UN/LOCODE) · routes · route-availability
│                 rate/fixtures: cost-model · rates
├── identity/     actors · claims-contract · entra-objects (TARGET terraform)
├── authorization/ authz-projection · policies.cedar · obligations · governance
├── agents/       catalog (the 3 repricing agents)
├── interfaces/   mcp/ (TARGET) · api/ (openapi.yaml per API) · a2a/
├── scenarios/    01-fx-flips-lane · 02-route-unavailable · 03-approval-loop · 04-combined-route-fx-shock
├── fixtures/     rfqs/ · fx/ · normalized-options · tokens/ · scenario-packs/ (5 reproducible worlds)
├── themes/       teaching · solarized-light · corporate-sample (passable colorscheme)
├── deploy/       the PLAN — GCP mapping · container strategy · environments
├── infra/        the ARTIFACTS — compose · caddy · terraform · cloudbuild · keycloak · entra (TARGET)
├── spikes/       repricing/policy-evaluation/ ★ REAL CODE — 7 tests green against a live, isolated cedar-agent (:8280)
└── traceability.yaml   proves the chain resolves end-to-end
```

## What's actually running (not just designed)

Three real, tested codebases exist today, all green:

- **`src/rfq_common/`** — the Phase 1 foundation library (models, jsonl, JWT/JWKS
  verify, PDP client + schema generator, theme renderer, clock/seed, base
  FastAPI/Typer apps · masterdata client). 49 tests, `uv run pytest`.
- **`spikes/repricing/policy-evaluation/`** — drives scenarios 01–04 + 3 failure
  injections through a live, isolated `cedar-agent` (port `:8280`, container
  `rfq-showcase-cedar-agent` — never the `:8180` instance cpm-eaop runs for its own
  work). 7 tests, `uv run pytest` (after `docker compose up -d`).
- **`src/mock-fx/`** — the first Phase 2 mock system, verified **actually running**:
  `uv run mock-fx serve` and hit it — real Swagger UI at `/docs`, APIKEY-gated
  `/exchange-rates/{base}/{quote}`, `/convert` (currency rounding, JPY-aware), `/admin/reset`.
  Now consumes masterdata via its real API (ADR-010) to validate currencies. 37 tests.
- **`infra/vault/` + `rfq_common.secrets`** — ADR-009's Vault-dev credential store,
  standing and seeded (`rfq-showcase-vault`, :8200); `mock-fx`'s API key comes
  from Vault, no hardcoded fallback.
- **`src/mock-masterdata/`** (ADR-010) — the masterdata source: 9 reference
  domains (Party/Location/Currency/Incoterm/Commodity/Equipment/UoM/DG-class/
  Payment-term), real data (UN/LOCODE, ISO 4217, Incoterms 2020, IMDG classes),
  verified live. Closes the original "no customer/carrier reference" gap —
  `RFQ`/`Quote`/`RouteOption` now carry `customer_id`/`carrier_id` referencing
  Party instead of embedding bare strings. 24 tests.
- **117 tests total, all green**, across `rfq_common` (49) · `mock-fx` (37) ·
  `mock-masterdata` (24) · `policy-evaluation` (7).

Building these surfaced and fixed **4 real bugs** pure design review missed: two
missing baseline policies (D10/D11), one missing "nothing is wrong" permit (D12),
and cedar-agent rejecting `is`-in-scope Cedar syntax (same issue cpm-eaop hit
historically) — plus a non-ASCII HTTP header bug in `rfq_common`. See each
component's own README for details.
