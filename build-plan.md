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

## Phase 1 — Foundations (`rfq_common`) · CRITICAL PATH · ✅ DONE

- ✅ **`rfq_common`** (`src/rfq_common/`, own uv package, 33 tests green):
  Pydantic entity models (`models.py`) · jsonl loader (`jsonl.py`) · IdP-agnostic
  JWT/JWKS verify, offline-testable (`verify.py`) · Cedar PDP client + admin +
  policy bundle + schema generator, path/namespace-parameterized (`pdp/`) · theme
  token model + CSS-var renderer (`theme.py`, ADR-007) · clock/seed determinism
  helpers (`clock.py`) · base FastAPI app (`app.py`) · base Typer CLI (`cli.py`).
- ✅ Schema generation verified to match the committed `agentic.cedarschema`
  byte-for-byte, generated from the real `authorization/authz-projection.yaml` +
  `business/actions.yaml`.
- ✅ **Entity / request assembly** — `pdp.entities` (ref/uid/action_ref), proven
  against 5 real decisions (D1, D4b forbid, D3b+D8 obligation-merge, D6) through
  the isolated cedar-agent (`spikes/repricing/policy-evaluation/`, :8280).
- **Exit — met, exceeded the stated bar:** schema PUTs into the isolated
  cedar-agent; **5** requests (not just one) evaluate to their expected decisions,
  including a forbid-beats-permit and an obligation-merge case; unit tests green
  (33/33, including 6 offline JWT tests against a real generated keypair).
- **3 real bugs caught by building this for real** (not just designed): D10/D11/D12
  missing policies, `is`-in-scope Cedar syntax rejection (mirrors a known cpm-eaop
  issue), non-ASCII banner text breaking an HTTP header (latin-1-only) — all fixed.
  See `src/rfq_common/README.md` + `spikes/repricing/policy-evaluation/README.md`.

## Phase 2 — Mock systems (backend · API · CLI) · IN PROGRESS

- ✅ **FX** — `src/mock-fx/` built, 21 tests green, verified **actually running**
  (`uv run mock-fx serve`): `/healthz`, real Swagger UI at `/docs`, APIKEY-gated
  `/exchange-rates/{base}/{quote}` with point-in-time lookup, `/admin/reset`. See
  `src/mock-fx/README.md`.
- ⬜ **CPQ** next (the `Quote.status` SoR — the mandatory approval frontend), then
  CRM/TMS/Rate/Workflow.
- 6 systems total over `rfq_common`, jsonl/fixture-baked, admin `reset`.
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
