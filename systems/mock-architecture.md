# Mock system architecture — capability matrix

Each mocked system is **one in-memory backend** (loaded from jsonl fixtures) with a
**defensible subset** of facets over that single store — not "everything for
everyone". Nothing here is implemented in this pass; this is the shape the spike
(`../spikes/repricing/`) would build.

## Principle: one backend, many facets

```text
jsonl fixtures ─► in-memory store ─┬─ REST API      (base contract)
                                   ├─ MCP server    (agent access, some systems)
                                   ├─ CLI           (deterministic ops for coding agents)
                                   └─ frontend      (human-touched systems only)
```

All facets read/write the **same** store — never fork state per facet.

**Every API ships an OpenAPI 3.1 `openapi.yaml`** (FastAPI-generated, committed to
`<system>/openapi.yaml`), with `x-domain-action`/`x-resource-type`/`x-authz-context`
extensions binding operations to the Cedar action vocabulary. See `../interfaces/api/`.

## Two planes — do not conflate them

- **Auth to the system** (APIKEY · SSO · client-credentials) = *how a caller reaches
  a backend*.
- **Authz of the action** (Cedar over the agent's resolved principal) = *whether the
  action is allowed*.

An MCP server's APIKEY lets the **server reach its backend**; it is **not** the
agent's identity. The agent's `mcp.connect` / `tool.call` is governed by the PDP.
This is the second of the two correlated boundaries (agent→tool, then tool→API).
**Humans SSO (Keycloak/Entra); agents use client-credentials/WIF, never interactive SSO.**

## Capability matrix

| System | Backend (jsonl) | REST API | MCP server | Auth | Frontend | CLI |
| --- | :--: | :--: | :--: | --- | :--: | :--: |
| **CRM** | ✓ | ✓ | ✓ `crm-mcp` | human **SSO** + agent client-creds | maybe (RFQ view) | ✓ |
| **TMS** | ✓ | ✓ | ✓ `tms-mcp` | agent client-creds / APIKEY | — | ✓ |
| **Rate** | ✓ | ✓ | ✓ `rate-mcp` | agent client-creds / APIKEY | — | ✓ |
| **CPQ** | ✓ | ✓ | ✓ `commercial-mcp` | human **SSO** (approval UI) + agent client-creds | ✓ **approval UI** | ✓ |
| **FX** | ✓ | ✓ (REST — the point) | ✗ (deliberately none) | **APIKEY** (machine) | — | ✓ |
| **Workflow** | ✓ | ✓ | ✓ `approval-mcp` | human **SSO** | maybe (task inbox) | ✓ |

Legend: ✓ = build · — = not needed · ✗ = deliberately excluded.

### Why each subset
- **FX** — no MCP, no SSO, no frontend: a narrow deterministic machine API, APIKEY-guarded.
  MCP is reserved for agent access to internal systems of record.
- **CPQ** — the only mandatory frontend: the human sets `Quote.status`
  (`approval_required → approved | rejected | revise`) here; that transition **is** the
  human decision (see `systems-of-record.yaml`). It also serves agents via MCP.
- **TMS / Rate** — no human surface: agents only, via MCP; APIKEY server→backend.
- **CRM / Workflow** — optional human surface (RFQ view / task inbox); primary access is MCP.

## Enterprise frontend features

A mocked system must look and behave like a real enterprise app, or the showcase
isn't convincing. Systems with a frontend (see UI-depth table below) implement:

- **SSO + session** — login/logout via Keycloak/Entra, session timeout. **Same IdP +
  same claim contract that governs the agents** — a human in the UI and an agent via
  MCP are governed consistently (`../identity/claims-contract.md`).
- **Role-gated UI** — menu, views, and buttons reflect the user's role. UI authZ
  **mirrors** the Cedar decision; it does not replace it.
- **List + detail views** — table with search / filter / sort / pagination; record
  detail with a **status/lifecycle badge**.
- **Actions = domain actions** — buttons map to the *same* domain actions (CPQ
  "Approve / Reject / Request revision" → `route-deviation.approve` / `Quote.status`).
  **No UI-only actions.**
- **Audit / history per record** — who did what when (matches the `audit-events`
  vocabulary in `../business/process.md`).
- **Dashboard / home** — counts + KPIs (e.g. Workflow: approvals pending).
- **Task inbox + badges** — Workflow / CPQ (approval_required count).
- **User / context indicator** — current user · tenant/org · role.
- **Cross-system deep-links** — RFQ (CRM) → Quote (CPQ) → Booking (TMS). Demonstrates
  the fragmented-SoR reality: links, not embeds.
- **Currency / locale formatting** — real here (EUR/CNY); i18n-ready.
- **Environment banner** — a visible `SHOWCASE` badge; version/build footer.
- **API docs link** — Swagger UI over the system's REST API.
- **Correlation-id display** — trace one decision across systems.
- **Polish** — empty / loading / error states · a11y basics · "reset demo data".

**Distinct-but-cohesive:** one shared component library/shell, a **per-system theme**
(name · logo · color). Each looks like its own product; all behave consistently.

### UI depth per system

| System | UI depth | Why |
| --- | --- | --- |
| **CPQ** | full | the approval UI — mandatory; humans set `Quote.status` here |
| **CRM** | full | RFQ / customer views |
| **Workflow** | full | task inbox |
| **TMS / Rate** | minimal read-only console (login + list/detail) | agent-facing; console for demo credibility |
| **FX** | none — status/health page + Swagger | machine service, APIKEY only |

## Per-system home

Each system's contract, fixtures, and mock spec live in its folder
(`crm/`, `tms/`, `rate/`, `cpq/`, `fx/`, `workflow/`). A top-level **scenario
runner CLI** (in `../spikes/repricing/`) drives a scenario across all backends +
the PDP, so a coding agent can run `01-fx-flips-lane` deterministically end-to-end.

## cpm-eaop patterns to reuse (when built)

- jsonl-loaded fixtures + deterministic seeding (`data/identity/*.jsonl`, `tools/seed_identity_data.py`).
- CLI as `python -m` entrypoints, `PYTHONPATH=src`, `package=false` (`src/spike/entra/__main__.py`).
- SSO providers already spiked (`app/spike/controlpanel/auth_providers/{keycloak,entraid}.py`).
- Agent identity via Keycloak client + WIF (`data/agents/*.yaml` `caller_identity`).
- The FX REST + MCP-tool→domain-action binding (`../interfaces/`).
