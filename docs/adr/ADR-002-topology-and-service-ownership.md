# ADR-002: Container topology and MCP-server ownership

Status: Accepted
Date: 2026-07-26

## Context

The implementation plan named ADR-002 as the decision that resolves three
things ahead of M4a/M5/M6: the MCP-server-to-business-system networking
model, the hostname/vhost convention for new services, and the
one-MCP-server-per-business-system ownership invariant — stated precisely
enough to not contradict the plan's own fixed 4-MCP-server scope, where
`qms-mcp` and `approval-mcp` both legitimately front `mock-qms`.

Unlike ADR-001, this decision was never written down before the topology
it governs got built — M6-pre, Track A, and M6 Track B all made these
calls ad hoc, in code and compose files, across several milestones. This
ADR is written retroactively, capturing what was actually decided and
built (verified against the real, currently-running deployment, not
aspirational), so the decision has a durable record and the mechanical
checks it requires have a named authority to point back to.

## Decision

### 1. Networking model: GATEWAY-FIRST, compose-DNS for everything else

Caddy is the **sole externally-published ingress** (port 443). Every
showcase service — mock backends, MCP servers, A2A agents — publishes no
host port at all; reachable only via Caddy's `*.eaop-logistics.localhost`
vhosts (external) or the shared `rfq-showcase` compose network's own DNS
(internal, peer-to-peer: an agent calling an MCP server, or an MCP server
calling its backend business system, addresses the other container by
compose **service name** directly). Caddy is never a service-mesh
hairpin — peer-to-peer traffic does not route through it.

Keycloak (`:8081`) and Vault (`:8200`) are the only two exceptions,
publishing host ports as **explicit, justified carve-outs** (admin
console access; seed-script/debug access) — not because any peer service
needs them that way. Every peer service reaches both by compose DNS
(`http://keycloak:8080`, `http://vault:8200`), never through Caddy or a
host port.

Two compose files, not one: `infra/compose.support.yaml` (platform layer
— Caddy, Keycloak, Vault, owns the shared `rfq-showcase` network) +
`infra/compose.showcase.yaml` (app layer — mock backends, 4 MCP servers,
3 A2A agents, joins the network as `external: true`). Separable on
purpose: the support stack changes rarely and can restart independently
of the app layer.

**Known gap, not yet closed by this ADR:** `cedar-agent` (the PDP every
`authorize_and_enforce()` call depends on) runs from a separate checkout
(`spikes/repricing/policy-evaluation`, outside this repo's tree) and was,
until a live M7 stabilization fix, never reachable from the `rfq-showcase`
network at all — every real authorization call in the deployed stack was
failing. Fixed live by joining the running container to the network
directly (`docker network connect --alias cedar-agent`) and wiring
`CEDAR_URL` into every MCP server/agent's environment
(`infra/compose.showcase.yaml`). This ADR records cedar-agent as
**compose-network-reachable but not compose-project-owned** — a real,
accepted asymmetry (its lifecycle is independent of the showcase's own
`up`/`down`), not something this ADR resolves further. A future milestone
that formally brings cedar-agent into `infra/compose.support.yaml` (its
own service block, image, or a build from a vendored copy) would close
this gap; not required for the showcase's current scope.

### 2. Hostname/vhost convention

One `https://<service>.eaop-logistics.localhost` vhost per externally
reachable service, `reverse_proxy`'d by Caddy to the real compose service
name and port (`infra/compose/Caddyfile`). Internal-only peer traffic
never uses these hostnames — compose DNS service names only
(`http://tms-mcp:8104`, not `https://tms-mcp.eaop-logistics.localhost`),
per §1's hairpin rule. `SERVICE_PUBLIC_URL` (M5.5's runtime configuration
contract) is set to the external vhost form for every service that has
one — the value a service advertises about itself (Agent Cards,
`/descriptor`) is its real, externally-reachable identity, distinct from
the internal address peers actually use to reach it.

### 3. Ownership invariant: action/resource disjointness, not
one-server-per-system

The blanket "exactly one MCP server per business system" rule an earlier
plan draft stated is **wrong** and already contradicted by the fixed
4-server scope: `qms-mcp` and `approval-mcp` both legitimately front
`mock-qms`. The real invariant, stated precisely:

> Two MCP servers may point at the same underlying REST API only if their
> **exposed** action/resource sets are provably disjoint.

"Exposed" means derived from `interfaces/mcp/tools.yaml` — the
tool→action mapping each **server** actually publishes — never from
`agents/catalog.yaml`'s `owned_actions`, which answers a different
question (`Agent -> may invoke tool`, not `MCP server -> exposes tool`).
Conflating the two graphs was a documented mistake to avoid from the
start, not a later correction.

**Mechanically checked, not asserted by convention**:
`src/qms-mcp/tests/test_adr002_disjointness.py` computes `qms-mcp`'s and
`approval-mcp`'s exposed action sets directly from `tools.yaml`
(excluding tools with no `action:` mapping — `create_approval_task`/
`get_approval_status`, neither agent-invokable per the capability-profile
review, so neither participates in the disjointness question either way)
and asserts `isdisjoint()`. Real sets today: `qms-mcp` = `{quote-price.
calculate, quote-variance.evaluate, route-cost.normalize}`,
`approval-mcp` = `{route-deviation.propose, route.recommend}` — disjoint,
verified, not incidental.

### 4. Transport-credential model for MCP-server-to-business-system hops

Each MCP server calls its wrapped business system using its **own**
workload credential (never the caller's) — a shared API key per business
system (`tms-api-key`, `rate-api-key`, `qms-api-key`), not a per-MCP-
server key, an explicitly **accepted weaker-than-per-workload-token**
granularity (decision #8). `qms-mcp` and `approval-mcp` sharing
`qms-api-key` is valid at the transport layer *only because* §3's
disjointness check already holds at the authorization layer — the shared
key documents transport, it does not itself relax the ownership
invariant. Every such edge, plus its accepted-weaker-mechanism status, is
enumerated mechanically by `tools/identity/gen_machine_identity_inventory.py`
(`data/identity/machine-identity-inventory.yaml` /
`docs/adr/machine-identity-inventory.md`) — this ADR is the authority that
inventory's generated notes point back to.

## Consequences

- `infra/compose.support.yaml` + `infra/compose.showcase.yaml` are the
  real, current implementation of §1 — already built, running, and
  live-verified (M6-pre, Track A, M7 stabilization pass) before this ADR
  was written down; this document is their retroactive authority, not a
  design that still needs building.
- Any future MCP server sharing an existing business system's REST API
  must add its exposed action set to a disjointness test matching
  `test_adr002_disjointness.py`'s pattern before shipping — a required
  mechanical gate, not optional.
- cedar-agent's network-membership gap (§1) is recorded as a known,
  accepted asymmetry, not resolved by this ADR — a candidate for a later,
  separate milestone if the showcase's ownership model changes (e.g. this
  repo starts vendoring its own cedar-agent instead of depending on a
  sibling checkout).
- `identity/credentials-inventory.yaml`'s existing shared-API-key notes
  (already written per-credential, before this ADR existed) are now
  formally grounded in §4 rather than standing as isolated per-credential
  judgment calls.
