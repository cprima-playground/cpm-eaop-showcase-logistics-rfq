# mission-control-api

M8's read-only control-plane API. Aggregates real, already-existing read
models — service registry, topology, health, policy, identity,
identity-drift, traces — behind a single versioned `/api/v1` surface.

**Never a source of truth.** Every field it serves traces back to a real
authority: a committed YAML file, a live service's own `/descriptor`,
cedar-agent, Terraform state on disk, or Tempo. **Never an authorization
decision** — it observes and reports, it never calls cedar-agent's real
decision endpoint (mechanically enforced,
`tests/test_no_authorization_decisions.py`).

See `docs/adr/ADR-005-control-plane-boundary.md` for the design
decisions (why polling instead of a REGISTER protocol, why `/decisions`
doesn't exist yet, the identity-drift/credential-health distinction,
the M8 access policy).

## Endpoints

All `/api/v1/*` routes are `GET`-only and require a valid bearer token
(the same Keycloak introspection path every MCP server uses — see D6 in
the ADR). `/healthz` and `/descriptor` are unauthenticated, matching
every other service in this repo.

| Endpoint | What it reports |
|---|---|
| `GET /api/v1/services`, `/services/{canonical_id}` | The 7 descriptor-bearing services, polled live |
| `GET /api/v1/topology` | Runtime-dependency edges + credential edges, two separate labeled layers |
| `GET /api/v1/health` | A broader roster: registry services + 5 `mock-*` business systems + Keycloak/cedar-agent/Vault |
| `GET /api/v1/policies`, `/policies/drift` | Declared Cedar policy/schema/obligation counts; drift vs. cedar-agent's live policy set |
| `GET /api/v1/identities` | Declared humans/agents/workloads, groups, capability profiles — never a secret value |
| `GET /api/v1/identity-drift` | Declared identity projections vs. raw Terraform state on disk (machine identities only) |
| `GET /api/v1/traces`, `/traces/{trace_id}` | Tempo-backed, filtered on `cedar.authorize` spans — lossy, not an audit log |

## Running

Part of `infra/compose.showcase.yaml`'s `control-plane` (or `full`)
profile:

```
docker compose -f infra/compose.support.yaml -f infra/compose.showcase.yaml --profile control-plane up -d --build
```

Reachable at `https://mission-control.rfq-showcase.localhost` once
Caddy picks up the vhost (`infra/compose/Caddyfile`).

## Tests

```
uv run pytest tests/
```

Real-stack tests (the live-endpoint checks documented in each commit
message) are exercised manually against the running compose stack, not
part of the automated `pytest` run — no test in `tests/` requires
Docker or a live Keycloak/Vault/Tempo to pass.
