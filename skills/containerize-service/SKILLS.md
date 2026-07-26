# Skill: containerize a service in this monorepo

How to add a Dockerfile (and, if new, wire it into `infra/compose.yaml`)
for any service under `src/` in cpm-eaop-showcase-logistics-rfq — mock
backend, A2A agent, or MCP server — so it works the same way locally
(Docker Compose behind Caddy) and on GCP (Cloud Run / Vertex AI Agent
Engine). Written from the pattern applied across all 13 real services
this repo has today (6 mock backends, 3 A2A agents, 4 MCP servers).

## Prerequisite reading

- `tmp/GATEWAY-FIRST-routing-analysis.md` — the architectural decision this
  skill implements: service identity is a **hostname**, routed by Caddy
  (or, on GCP, Apigee/Cloud Run's own URL). A container's bind port is an
  internal implementation detail, never part of external identity.
- `src/rfq_common/rfq_common/settings.py` (`ServiceSettings`) and
  `src/rfq_common/rfq_common/service_resolver.py` — already provide the
  bind-vs-advertised split; a new service should use these, not invent its
  own env-var parsing.

## Step 1 — identify which of the two service families it is

Every service in `src/` is one of:

**A. Mock backend** (FastAPI + typer CLI, has a `serve` subcommand) —
`mock-fx`, `mock-tms`, `mock-rate`, `mock-masterdata`, `mock-qms`,
`ops-dashboard`. Entry point: `uv run <name> serve --host 0.0.0.0`.
Port comes from `serve(port: int = int(os.environ.get("SERVICE_PORT", <N>)))`
— a plain default expression in the CLI, not `ServiceSettings` (these
predate M5.5 and haven't been migrated; that's fine, don't migrate them
as a side effect of containerizing).

**B. A2A agent or MCP server** (`main()` in `cli.py` calls `uvicorn.run`
directly, no subcommand) — `lane-evaluation-agent`, `route-decision-agent`,
`commercial-normalization-agent`, `tms-mcp`, `rate-mcp`, `qms-mcp`,
`approval-mcp`. Entry point: `uv run <name>` (bare). Port/host come from
`SERVICE_HOST`/`SERVICE_PORT` (canonical) with `A2A_HOST`/`A2A_PORT`
legacy-compat fallback — every one of these should have a
`_resolve_host_port()` helper in `cli.py` (small, testable, extracted
specifically so this fallback logic isn't buried inline in `main()`
alongside its Keycloak self-check). If a new MCP server doesn't have this
helper yet, add it first (copy from `tms_mcp/cli.py`), plus the 3-case
regression test (copy from `src/tms-mcp/tests/test_cli_port_env.py`).

## Step 2 — check `pyproject.toml`'s `[project.scripts]`

Confirms the exact CLI entry point name (always matches the directory
name in this repo, e.g. `src/tms-mcp/pyproject.toml` → `tms-mcp = "tms_mcp.cli:main"`)
and confirms `[tool.uv.sources] rfq-common = { path = "../rfq_common", editable = true }`
is present — this is why the Dockerfile can't use the service's own
directory as build context (see Step 3).

## Step 3 — write `src/<service>/Dockerfile`

Repo-root build context is required, because `uv sync` needs to resolve
the editable `../rfq_common` path dependency — that means `COPY` inside
the Dockerfile must reach `src/rfq_common` as a sibling of `src/<service>`,
which only works if Docker's build context is the repo root, not
`src/<service>` itself:

```
docker build -f src/<service>/Dockerfile .
```

**Template — mock backend family (has `serve --host/--port`):**

```dockerfile
FROM python:3.12-slim
WORKDIR /app

COPY src/rfq_common /app/src/rfq_common
COPY src/<service> /app/src/<service>
WORKDIR /app/src/<service>

RUN pip install --no-cache-dir uv && uv sync --frozen

ENV SERVICE_PORT=<default-port>
EXPOSE <default-port>
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ[\"SERVICE_PORT\"]}/healthz', timeout=3)"

CMD ["uv", "run", "<service>", "serve", "--host", "0.0.0.0"]
```

**Template — A2A agent / MCP server family (bare `main()`):**

```dockerfile
FROM python:3.12-slim
WORKDIR /app

COPY src/rfq_common /app/src/rfq_common
COPY src/<service> /app/src/<service>
WORKDIR /app/src/<service>

RUN pip install --no-cache-dir uv && uv sync --frozen

ENV SERVICE_HOST=0.0.0.0
ENV SERVICE_PORT=<default-port>
EXPOSE <default-port>
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://localhost:{os.environ[\"SERVICE_PORT\"]}/healthz', timeout=3)"

CMD ["uv", "run", "<service>"]
```

**Why these specific choices:**

- `python:3.12-slim`, not `alpine` — matches every existing `pyproject.toml`'s
  `requires-python`, and avoids musl/glibc wheel-compatibility surprises
  with `httpx`/`uvicorn`'s compiled deps.
- `HEALTHCHECK` uses `python -c` with `urllib.request`, not `curl` —
  `python:3.12-slim` doesn't ship `curl`, and adding it is an unnecessary
  extra `apt-get` layer when the interpreter already in the image can do
  the same GET.
- `ENV SERVICE_PORT=<N>` is set in the Dockerfile (not left to compose) so
  the image is runnable standalone (`docker run <image>` just works) —
  compose can still override it per-service if ever needed, but doesn't
  have to.
- **No `EXPOSE`-adjacent `ports:` mapping is decided here** — that's a
  compose-level decision (Step 4), and for most services the answer is
  "none, Caddy or compose-internal DNS reaches it," not "publish a host
  port." `EXPOSE` alone is documentation to Docker/humans, not a network
  decision.
- Non-root user, build-metadata labels (service/version/commit) are a
  deliberate **future** hardening step, not part of this skill's baseline
  — see `tmp/GATEWAY-FIRST-routing-analysis.md` §9 for why they're deferred,
  not forgotten.

## Step 4 — wire it into `infra/compose.yaml` (GATEWAY-FIRST)

Do **not** add a `ports:` host-publish mapping by default. The target
topology:

```
browser / external client → Caddy :443 → container (compose service name)
agent/MCP peer traffic    → compose DNS (service name:port) directly, no Caddy hairpin
```

Add the service to `infra/compose.yaml` with:
- `build: {context: ., dockerfile: src/<service>/Dockerfile}`
- `environment:` — at minimum `SERVICE_PUBLIC_URL: https://<service>.rfq-showcase.localhost`
  so `ServiceSettings.public_url` (and therefore `/descriptor` and any A2A
  Agent Card) advertises the Caddy-facing hostname, not a raw container
  DNS name or bind port.
- no `ports:` — join the shared network only, resolve by service name.
- correct `profiles:` bucket (`core` for the 6 mock backends + keycloak +
  vault, `mcp` for the 4 MCP servers, `agents` for the 3 A2A agents,
  `full` for everything).

Only add a **host** port publish for a service if it's genuinely one of
the justified exceptions: the edge itself (Caddy, `443`), an admin UI a
developer needs direct access to bypassing TLS friction (Keycloak, Vault),
or an explicitly-a-dev-tool (`a2a-inspector`). Everything else stays
internal-only — this is the thing a topology test should assert (see
`src/rfq_common/tests/` for where that lives once written).

Add a matching route to the compose-topology Caddyfile (not
`infra/caddy/Caddyfile`, which is the older host-process-fronting one —
the compose-topology file routes to compose service DNS names instead of
`host.docker.internal`):

```
https://<service>.rfq-showcase.localhost {
    import friendly_errors
    reverse_proxy <service>:<port>
}
```

## Step 5 — GCP target (test/demo/prod)

Per ADR-008 + `deploy/containers.md`: mock backends and MCP servers run on
**Cloud Run**; A2A agents run on **Vertex AI Agent Engine**. Neither
requires anything different in the Dockerfile itself — Cloud Run in
particular expects exactly this shape (a container listening on a port it
reads from its own env, here `SERVICE_PORT`/`PORT`-compatible). The
Dockerfile written in Step 3 should need zero changes to deploy to Cloud
Run; only `infra/compose.yaml`'s local-only concerns (the shared bridge
network, `SERVICE_PUBLIC_URL` pointing at `*.rfq-showcase.localhost`) are
dev-specific and get replaced by Cloud Run's own URL / Apigee routing at
that layer, not the container image.

## Step 6 — verify

```sh
# standalone build+run
docker build -f src/<service>/Dockerfile -t <service> .
docker run --rm -p 18080:<default-port> <service>
curl http://localhost:18080/healthz   # expect 200

# inside the full topology
docker compose -f infra/compose.yaml --profile <bucket> up --build
curl -k https://<service>.rfq-showcase.localhost/healthz   # through Caddy
```

Also re-run the service's own `uv run pytest` — containerizing should
never require touching business logic, so its existing suite must stay
green untouched.
