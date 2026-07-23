# Build plan — design → running → demoable

Phased plan to build, run, and demo the showcase. Complements `TODO.md` (which lists
missing *design docs*); this lists *work*. Nothing here is built yet. Each phase has
**deliverables** + an **exit criterion**. Critical path: **Phase 1** (`rfq_common` +
schema-gen + entity assembly) — without it the authz model can't be exercised.

## Phase 0 — Lock decisions

- ✅ **Agent identity** — resolved env-conditionally: Keycloak client-creds (dev) ·
  WIF→Entra (test/prod). `deploy/environments.md` + ADR-006 §4 (accepted).
- ✅ **Persistence** — resolved: in-memory/SQLite (dev, zero-cost) · Firestore
  hosted-only (free tier).
- ✅ **Environments** — dev (local·Keycloak·free) → test (personal GCP·Entra·WIF) →
  demo/prod (corporate GCP·Entra). `deploy/environments.md`.
- ✅ **Agent runtime** — **Vertex AI Agent Engine (ADK)** on GCP; **local via the ADK
  runner** in dev (same code), LLM stubbed for zero-cost determinism. ADR-008.
- ✅ **Second boundary** — **out of scope**: the showcase governs agent→tool (Cedar);
  tool→API is implementation, not modeled. ADR-008 (Related).
- ✅ **Domain ADRs 001–005** — written + accepted (scope · SoR-boundaries ·
  agent/tool-boundaries · authorization-model · human-approval-boundaries).
- **Exit:** ✅ **met** — all eight ADRs accepted; Phase 0 complete. Next: Phase 1 (`rfq_common`).

## Phase 1 — Foundations (`rfq_common`) · CRITICAL PATH

- `rfq_common`: Pydantic entity models · jsonl loader · JWT/JWKS verify (reuse cpm-eaop
  `entra/verify.py`) · PDP client · base FastAPI + base Typer app · clock/seed helpers ·
  theme token model + CSS-var renderer (ADR-007).
- Copy `generate_cedar_schema.py`; generate the showcase `agentic.cedarschema` from
  `authorization/actions.yaml` + `authz-projection.yaml`.
- **Entity / request assembly** — domain snapshots → Cedar entities + context.
- **Exit:** schema PUTs into a local `cedar-agent`; one request (scenario 01 step)
  evaluates to the expected decision; unit tests green with a mock PDP.

## Phase 2 — Mock systems (backend · API · CLI)

- 6 systems over `rfq_common`, jsonl fixtures baked, admin `reset`. **Order: FX first**
  (simplest vertical slice), then **CPQ** (the `Quote.status` SoR), then CRM/TMS/Rate/Workflow.
- **Exit:** each system serves REST + Typer CLI; loads its fixtures; `reset` restores baseline.

## Phase 3 — Governed edges (MCP + PDP)

- MCP server per system (APIKEY→backend); control-plane decision service; wire
  `mcp.connect`/`tool.call` through the PDP; obligation resolver + PEP (`enforce`).
- **Exit:** an agent tool call is authorized by Cedar end-to-end; obligations enforced;
  a forbid denies (deny-precedence) as in scenario 04.

## Phase 4 — Agents + A2A

- The 3 agents (per `agents/catalog.yaml`) written to the **ADK**; run **locally via
  the ADK runner** (LLM stubbed, deterministic); A2A chain lane→commercial→route;
  delegation bounded to depth 1. Same code deploys to Vertex Agent Engine (ADR-008).
- **Exit:** the chain runs on fixtures; delegation governed; FX read → normalize →
  recommend produces the scenario-01 recommendation.

## Phase 5 — Frontends + SSO + theming

- Jinja2 + HTMX + Tailwind shell; per-system UI depth (`systems/mock-architecture.md`);
  Keycloak + Entra SSO (Auth Code + PKCE); `THEME`/`THEME_PATH` skinning (ADR-007);
  CPQ approval UI writes `Quote.status`.
- **Exit:** a human logs in, sees role-gated views, approves in the CPQ UI (status
  transition); `THEME=solarized-light` re-skins the whole showcase with no rebuild.

## Phase 6 — Scenario runner + determinism

- The runner CLI: `rfq scenario apply <pack>` → reset → apply (absolute) → pin `NOW` →
  re-PUT PDP entities → stamp `run_id` (`RUNNING.md`).
- **Exit:** `scenario apply combined-route-and-fx-shock` deterministically yields the
  scenario `.yaml` `then` block; re-runs are byte-stable.

## Phase 7 — Containers · local · GCP

- In **`infra/`**: Dockerfiles (`rfq/base` + per service); `compose.yaml` (profiles
  core/agents/sso/full); Caddy edge (`infra/caddy/Caddyfile`); keycloak realm;
  cedar-agent compose. Then `infra/terraform` + `infra/cloudbuild`: Cloud Build →
  Artifact Registry → Cloud Run (min-instances=1, max=1 for mocks/PDP) + Apigee +
  WIF/Secret Manager. (`deploy/` holds the plan; `infra/` the artifacts.)
- **Exit:** `docker compose up full` runs the whole showcase locally behind Caddy; a GCP
  deploy runs one scenario end-to-end.

## Phase 8 — Demo + CI

- Demo storyboard (the "one event → everything" journey) + live evidence (decision
  trail · audit events · triggered thresholds).
- CI: build images → compose up → run scenario 04 → assert the `then` block.
- **Exit:** reproducible stakeholder demo + green CI on every push.

## Cross-cutting (land alongside the relevant phase)

Threat model + NFRs + risks (Phase 0–1) · `policy-test-cases.yaml` (Phase 3) ·
observability / correlation-id (Phase 3–4) · kill-switch runtime (Phase 3) ·
grants hot-path if adopted (Phase 3). See `TODO.md`.

## Sequencing at a glance

```text
0 decide → 1 rfq_common+schema+entities → 2 mocks(FX,CPQ first)
→ 3 MCP+PDP → 4 agents+A2A → 5 frontends+SSO+theme
→ 6 scenario runner → 7 containers(local→GCP) → 8 demo+CI
```
