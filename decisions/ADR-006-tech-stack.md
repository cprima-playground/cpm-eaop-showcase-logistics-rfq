# ADR-006 — Mock-system tech stack

**Status:** accepted (agent-identity resolved env-conditionally — Decision 4 + `../deploy/environments.md`).
**Context:** every mock system needs a backend + API + CLI + (some) frontend + SSO,
built consistently and reusing cpm-eaop patterns. `NOW`/seed determinism (`../RUNNING.md`)
and the claim contract (`../identity/claims-contract.md`) constrain the choices.

## Principles

- **Python-centric.** One language for backend/API/CLI so a coding agent operates the
  whole stack. Reuse cpm-eaop (FastAPI · Pydantic · httpx · pyjwt · msal · uv).
- **Pydantic models are the single source of truth** for entities — shared by the API,
  the CLI, jsonl loading, and validation. No parallel schemas.
- **One backend, many facets** (API/CLI/frontend over the same in-memory store —
  `../systems/mock-architecture.md`).

## Decision 1 — Backend · API · CLI (confirmed)

| Concern | Choice | Note |
| --- | --- | --- |
| API | **FastAPI + Uvicorn** | matches cpm-eaop `principal-api`, `control-panel` |
| Models / validation | **Pydantic v2** | SSOT for entities; jsonl → Pydantic on boot |
| CLI | **Typer** | same-author as FastAPI, Pydantic-friendly; supersedes cpm-eaop's argparse |
| HTTP client | **httpx** | FX API + inter-service + PDP client |
| Data store | **in-memory, loaded from jsonl** | deterministic; Firestore optional for HITL persistence (deploy open Q) |
| Env / packaging | **uv** | global rule; a shared `rfq_common` lib + one thin package per system |
| Determinism | injected **clock (`NOW`)** + fixed **seed** | `../RUNNING.md`; clock is load-bearing for D1/D2 |

`rfq_common` holds: Pydantic entity models · jsonl loader · JWT/JWKS verify · PDP
client · base FastAPI app + base Typer app · clock/seed helpers. Each mock system is
thin on top.

## Decision 2 — Frontend (recommended)

**Server-rendered: FastAPI + Jinja2 + HTMX + Tailwind** (per-system theme via Tailwind
config / DaisyUI). Python-only, no JS build toolchain; HTMX gives enough interactivity
for the QMS approval UI (status transitions, task inbox) and list/detail views.

- **Why not a SPA (React/Vue + Vite):** needs a Node toolchain, heavier, overkill for
  mocks. Escalate to a per-system SPA only if a system later needs rich client state.
- **Distinct-but-cohesive:** one shared Jinja base + component partials; each system a
  Tailwind theme (name · logo · color).
- UI depth per system per `../systems/mock-architecture.md` (QMS/CRM/Workflow full;
  TMS/Rate minimal; FX none).

## Decision 3 — User SSO (confirmed)

**OIDC Authorization Code + PKCE** against **Keycloak** and **Entra ID**; validate the
JWT via JWKS (**pyjwt[crypto]** + OIDC discovery — reuse cpm-eaop `src/spike/entra/verify.py`
+ `app/spike/controlpanel/auth_providers/{keycloak,entraid}.py`). Session via Starlette
`SessionMiddleware`. **Authlib** for the OIDC client flow. Humans only; agents never
interactive-SSO.

Both IdPs resolve through the **one claim contract** → `resolve_principal`. UI authZ
(role-gated views) reflects the same principal the PDP evaluates — auth to the system
≠ authz of the action.

## Decision 4 — Agent service accounts (RESOLVED — env-conditional)

**Resolved (`../deploy/environments.md`):** **dev** = Keycloak client-credentials;
**test + prod** = **WIF → Entra** (GCP SA federates, no stored secret). Both emit an
`azp` the claim contract resolves to `kind=agent`. Options/rationale below.


Agents authenticate as services (not interactive SSO) and must emit an **`azp`** the
claim contract classifies as `kind=agent`. Options:

| Option | Mechanism | Pros | Cons |
| --- | --- | --- | --- |
| **A. Keycloak client-credentials** *(recommended for the spike)* | confidential client per agent (client_id/secret) | simplest; already in `../agents/catalog.yaml` `caller_identity.keycloak_client`; matches cpm-eaop `control-panel-svc` | stored secret |
| **B. Workload Identity Federation** *(target)* | agent platform identity (GCP SA/OIDC) federates → Keycloak/Entra token, **no stored secret** | no secrets; matches cpm-eaop `hello-agent-gcp` + infra WIF | more setup |
| C. Entra app-only / federated credential | Entra client-credentials or federated cred | Entra-native | second IdP path |

**Recommendation:** **A now** (fast, unblocks the spike) → **B (WIF) as target** (no
secrets) — mirrors the `infra/entra` decision (client secret now, WIF flagged next).
Confirm the target so the identity fixtures + `deploy/` WIF plan are authored to match.

## Consequences

- **Every API ships an OpenAPI 3.1 `openapi.yaml`** (FastAPI-generated, committed to
  `../systems/<system>/openapi.yaml`) with `x-domain-action` extensions — one shared
  action vocabulary across API/MCP/agent/Cedar. See `../interfaces/api/`.
- Update `../systems/mock-architecture.md` facets to name concrete tech.
- `identity/` fixtures + `deploy/terraform` (Keycloak clients / WIF) follow Decision 4.
- Divergence from cpm-eaop to note: **Typer** (vs argparse) and **Jinja2/HTMX/Tailwind**
  (vs the control-panel's minimal TS). Everything else is parity.
