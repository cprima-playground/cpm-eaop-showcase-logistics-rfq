# ADR-005: Control-plane boundary (Mission Control API)

Status: Accepted
Date: 2026-07-26

## Context

`tmp/controlplane.md` — a separate architectural design pass — proposed
separating control plane, data plane, and management APIs more
explicitly than the showcase's original, narrower M4b scope (a minimal
read-only admin surface, never built). This ADR records the decisions
made implementing M8, the first concrete slice of that larger design: a
standalone, read-only `src/mission-control-api/` service.

## Decision

### 1. Control plane vs. data plane

```text
CONTROL PLANE          Mission Control API (/api/v1) -- read models only
                              |
                        desired/observed metadata
                              v
DATA PLANE              Gateway -> A2A agents / MCP servers -> local PEP -> Cedar -> SoR
```

Mission Control never sits in the data plane's request path. Standing
invariant, binding beyond M8: loss of Mission Control or its registry
must never interrupt established data-plane communication. Agents/MCP
servers resolve a peer's endpoint via `rfq_common.service_resolver`
once (or cached) — never a synchronous call to Mission Control per
A2A/MCP invocation.

### 2. Mission Control is a projection, never a source of truth

```text
Identity YAML / IdP     -> identity truth
agents/catalog.yaml     -> capability truth
Cedar policies          -> authorization truth
business systems        -> business truth
runtime /descriptor     -> live instance truth
Mission Control         -> control-plane PROJECTION of all the above
```

Every field Mission Control serves must be traceable to one of these
real authorities. It never becomes a second copy of any of them.

### 3. Discovery: poll, don't REGISTER

Mission Control polls each service's existing `GET /descriptor` (M5.5).
No REGISTER endpoint, no heartbeat, no deregister in M8 — all three are
writes, and M8's defining constraint is read-only. Polling produces a
real registry read model (`ObservedServiceRegistry`, deliberately named
to distinguish it from a future `AuthoritativeRuntimeRegistry`) without
making service availability depend on Mission Control being up.

### 4. "Discoverable != authorized"

```text
Identity    -> who
Registry    -> where/how
Capability  -> what
Cedar       -> may
Credential  -> proof
```

Registry and topology views carry no implication of permission. Cedar
alone answers whether a caller may use an edge Mission Control shows it
can see.

### 5. `/api/v1/traces`, not `/api/v1/decisions`

```text
/traces
  -> operational observability
  -> best-effort / potentially sampled
  -> not authoritative
  -> not an audit log
```

No append-only decision log exists in this repo. Building one requires
deciding, first: decision event schema, sink, retention, PII/redaction,
tamper evidence, access control, export/compliance requirements —
and would make Mission Control a source of truth, contrary to decision
#2. `/api/v1/traces` proxies Tempo instead; `/api/v1/decisions` is
deliberately absent, not stubbed.

### 6. Identity-drift vs. credential health

Two different questions, only one answered by M8:

```text
identity drift      -> declared identity vs. provisioned identity (Terraform state on disk)
credential health   -> can this workload authenticate successfully right now? (a live grant check)
```

`GET /api/v1/identity-drift` answers the first, credential-free (both
sides are files on disk) — machine identities only, no `severity` field
(severity is a policy judgement, not built here). Credential health
(`rfq_common.pep.preflight.preflight_machine_identity`) answers the
second and requires reading every workload's Vault secret — Mission
Control's general API process deliberately never does this. A future
credential-health check, if built, belongs to a separate, narrowly
scoped worker, not this service.

Transitional posture, stated explicitly: reading raw `.tfstate` files
is credential-free but not a good long-term architecture — state files
can carry sensitive material even when this diff never touches it. A
future milestone should replace this with a sanitized, generated
provisioning projection instead of reading Terraform state directly.

### 7. M8 access policy (not RBAC)

```text
unauthenticated -> deny
authenticated   -> read-only access
mutation        -> unavailable (no write routes exist in M8 at all)
```

Every `/api/v1/*` route requires a valid bearer token (the same
Keycloak introspection path every MCP server uses); no Cedar check,
every authenticated principal sees the same data. Never called "RBAC"
— it isn't one. Two hard constraints regardless: never expose secrets,
credentials, raw tokens, or secret references; these endpoints are
authenticated internal metadata, not a public API. Fine-grained
control-plane authorization (dedicated actions like
`control-plane.identity.read`) is intentionally deferred to a later
milestone — `test_frozen_action_vocabulary.py` already establishes the
action vocabulary is governed, needing its own ADR, not a silent edit.

### 8. Contract discipline

The committed OpenAPI contract (`interfaces/api/mission-control-v1.openapi.json`)
is generated from the live app and compared on every test run via
canonicalized JSON (parsed and re-sorted, not raw bytes — a library's
own field-ordering change must never fail this test on its own).
`/api/v1` is versioned as a stable path prefix; no non-`GET` operation
exists in v1, mechanically asserted.

## Consequences

- `src/mission-control-api/` ships standalone, verified against the
  real running stack, before any consumer (e.g. `ops-dashboard`)
  migrates to it — that migration is a separate, later milestone (M9),
  with its own acceptance criteria.
- Two real, separate infra gaps were found and only partially closed
  while building this: cedar-agent's and Tempo's compose networks were
  both unconnected to the showcase network (fixed via direct
  `docker network connect`, not a compose-project merge); most showcase
  services still have no OTLP wiring to the observability collector at
  all, so `/api/v1/traces` will show real showcase authorization
  activity only once that separate, larger gap is closed.
- A real, pre-existing bug (`mock-fx` missing `MASTERDATA_URL`,
  crash-looping) was found and fixed by this milestone's own health
  check — the kind of finding this endpoint exists to surface.
- Future milestones that build on `ObservedServiceRegistry` must
  preserve decision #1's standing invariant even after a real
  REGISTER/HEARTBEAT authority exists.
