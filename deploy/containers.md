# Containers — strategy for the whole showcase

`TARGET` — plan only. **One image per component; the same image runs locally
(docker compose) and on GCP (Cloud Run)** → dev/prod parity. Mirrors cpm-eaop
(`infra/cedar-agent/docker-compose.yml`, `infra/keycloak`, `infra/caddy`).

## Why containers here

- **Parity** — the image demoed on a laptop is the image deployed to Cloud Run.
- **Determinism** — images are immutable; boot = baseline; fixtures (jsonl) are baked
  in. A scenario is applied at runtime, never by editing an image (`../RUNNING.md`).
- **Isolation of governed edges** — each MCP server and agent is its own container, so
  `agent→tool→backend` are real network hops a PEP can sit on.
- **One command up** — `docker compose up` brings the whole world; profiles bring subsets.

## Container inventory

| Component | Image | Local (compose) | GCP |
| --- | --- | --- | --- |
| 6 mock systems (crm·tms·rate·qms·fx·workflow) | `rfq/<system>` (FastAPI+Typer+SSR) | `:80xx` each | Cloud Run (one service each) |
| 5 MCP servers (crm·tms·rate·commercial·approval) | `rfq/<name>-mcp` | `:81xx` | Cloud Run |
| 3 agents (lane·commercial·route) | `rfq/<agent>` | `:82xx` | Cloud Run (or Vertex Agent Engine) |
| Cedar PDP | `permitio/cedar-agent` (upstream) | `:8180` | Cloud Run (private) |
| Control-plane decision svc | `rfq/control-plane` (FastAPI) | `:8090` | Cloud Run (private) |
| Keycloak (SSO) | `quay.io/keycloak/keycloak` + realm import | `:8080` | Cloud Run / GKE |
| Edge / PEP | `caddy` (local) → **Apigee** (GCP) | `:8000` | Apigee (managed, not a container) |
| Scenario runner | `rfq/runner` (Typer CLI) | one-shot | Cloud Run Job / local |

CLI is **not a separate image** — it's the same system image with a Typer entrypoint
(`docker run rfq/qms cli ...`).

## Build strategy

- **Shared base image** `rfq/base` — Python + uv + `rfq_common` (Pydantic models · jsonl
  loader · JWT verify · PDP client · base FastAPI/Typer app · clock/seed). Each service
  `FROM rfq/base`, adds its thin package + fixtures.
- **Multi-stage** (uv build → slim runtime); fixtures (`systems/<s>/fixtures`, `fixtures/`)
  COPYed in. Small, reproducible images.
- Build: **Cloud Build** (GCP) + local `docker build`; push to **Artifact Registry**.

## Local orchestration (docker compose)

- One `deploy/compose.yaml` (sketch: `compose.sketch.yaml`) with all services on one
  network; discovery by name (`crm:8000`, `cedar-agent:8180`, …).
- **Profiles**: `core` (systems+PDP), `agents`, `sso`, `full`. `just up [profile]`.
- Determinism env injected into every container: `NOW` (pinned clock), `SEED=42`,
  `CEDAR_AGENT_URL`, `OIDC_ISSUER`. APIKEYs from a local `.env` (Secret Manager on GCP).
- cedar-agent is reloaded via the bootstrap (`cedar-load`) on `scenario apply` — **not**
  restarted (restart wipes its in-memory schema/policies).

## Caddy — the local edge (dev)

Caddy is the single local entry point, standing in for **Apigee** on GCP. Reuses the
cpm-eaop `infra/caddy` pattern. It gives, on the dev box:

- **One entry point** — all services behind `:443`; no juggling ports.
- **Per-system hostnames** — `crm.localhost`, `qms.localhost`, … → each frontend gets
  its own origin (reinforces the distinct-but-cohesive branding; keeps cookies/SSO
  per-system clean).
- **Automatic local HTTPS** — Caddy's internal CA. **SSO needs https** for OIDC
  redirect URIs; Caddy provides it with no manual certs.
- **Local PEP analog** — a place to add JWT checks / headers before proxying, the way
  Apigee VerifyJWT sits in front on GCP.

### Caddyfile (sketch)

```caddyfile
{
    local_certs                      # internal CA -> https on *.localhost
}

crm.localhost      { reverse_proxy crm:8000 }
tms.localhost      { reverse_proxy tms:8000 }
rate.localhost     { reverse_proxy rate:8000 }
qms.localhost      { reverse_proxy qms:8000 }        # approval UI
workflow.localhost { reverse_proxy workflow:8000 }
fx.localhost       { reverse_proxy fx:8000 }         # API only
keycloak.localhost { reverse_proxy keycloak:8080 }
api.localhost      { reverse_proxy control-plane:8090 }   # PEP -> control plane
```

On GCP these hostnames become Cloud Run URLs / custom domains behind Apigee; the
Caddyfile routes map 1:1 to Apigee routes.

## Local → GCP parity

| Local (compose) | GCP |
| --- | --- |
| service on the compose network | Cloud Run service (private ingress + VPC connector) |
| Caddy edge | Apigee (VerifyJWT · quotas · routing) |
| `.env` secrets | Secret Manager |
| `docker build` | Cloud Build → Artifact Registry |
| `NOW`/`SEED` env | same env vars on Cloud Run |
| `scenario runner` container | Cloud Run **Job** |

Same images both sides; only ingress, secrets, and the edge differ.

## Cost — zero in development

Development runs **entirely locally** (`docker compose` + Caddy + local Keycloak +
`cedar-agent`). **No GCP, no Firestore, no cost.** GCP resources exist only for a
*hosted* demo. Persistence in dev: in-memory (default) or **SQLite**; the **Firestore
emulator** is free if you want that API. A hosted demo's only real cost is the warm
`min-instances=1` instance — **scale to zero when not demoing**.

## Cloud Run runtime settings (hot instances)

Cloud Run scales to zero by default (cold starts). For a live demo keep instances
warm:

| Setting | Value | Why |
| --- | --- | --- |
| `--min-instances` | `1` | no cold start — instance stays warm |
| `--cpu` allocation | **always allocated** | background work between requests (agent polling `Quote.status`, A2A loop) |
| `--max-instances` | `1` (mocks + PDP) | in-memory state isn't durable across instance **replacement**; pin to one so a demo's baked state stays put |
| `--concurrency` | modest | single warm instance handles the demo load |

Caveats:
- `min-instances` avoids cold starts but the autoscaler can still **replace** an
  instance (deploy/health) → in-memory state resets. Pin `max-instances=1` for the
  mocks/PDP during a demo. For state that must survive the HITL wait (`Quote.status`):
  **SQLite** (local file, zero cost) is enough for the showcase; **Firestore** only if
  a hosted demo needs durability (free tier is generous; dev uses the **emulator**).
- **Cost:** `min-instances=1` bills a warm instance — **scale to zero when not
  demoing.** Development never touches GCP (see below).
- Run **cedar-agent as a Cloud Run sidecar** of `control-plane` (multi-container
  instance) so they share one warm lifecycle; `min-instances=1` keeps the loaded
  schema/policies alive (reload-not-restart still applies).

## Determinism in containers (recap)

Immutable image → baseline on boot · fixtures baked in · `NOW`+`SEED` via env ·
admin `reset` + `scenario apply` at runtime · cedar-agent re-PUT (never restart) ·
`run_id` stamped. See `../RUNNING.md`.

## Planned files

Strategy lives here in `deploy/`; the runnable/provisioned artifacts live in the
sibling **`../infra/`** (see `../infra/README.md`):

```text
deploy/containers.md         ← this strategy doc
../infra/
├── compose.sketch.yaml      # the local topology
├── caddy/Caddyfile          # local edge: per-system *.localhost + local HTTPS
├── dockerfiles/base.Dockerfile + <service>.Dockerfile
├── terraform/               # Cloud Run · Artifact Registry · Apigee · Secret Manager · WIF
└── cloudbuild/              # image builds
```
