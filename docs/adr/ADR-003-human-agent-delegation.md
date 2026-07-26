# ADR-003: Human-to-agent delegation record

Status: Accepted
Date: 2026-07-26

## Context

`agents/catalog.yaml`'s `can_call` graph and `authorization/policies.cedar`'s
`agent-may-delegate-per-catalog` policy already govern agent-to-agent A2A
authority (M3.5/M5/M6b) — a fixed, catalog-declared graph, not something a
human grants at request time. What's still missing is the other kind of
delegation the roadmap always named separately: a **human** authorizing an
**agent** to act, bounded in scope and time, with the human remaining
accountable and traceable through every downstream hop.

This was explicitly deferred (implementation plan's decision area #7,
`ADR-003 (unallocated for now)`) until real M5/M6b A2A traffic existed to
design against, and until human identity resolved correctly across both
IdPs (M7 item 1) — both are now true. `context["delegated_by"]`
(`rfq_common.pep.enforce.AuthorizedContext`) already exists as an
audit-trail field and, per its own docstring, **carries zero authorization
weight today** — any caller can put any string there. This ADR resolves
what a *verified* delegation looks like; it does not retroactively change
`delegated_by`'s existing provenance-only behavior for callers that don't
yet establish a real delegation.

## Decision

### 1. Delegation is a signed, bounded, verifiable authority grant — a
distinct concept from identity, provenance, and execution context

Four things stay separate, always:

```text
authenticated principal   -- who executes this hop
delegation issuer         -- who granted authority
delegation scope          -- what authority was granted
provenance                -- how this request got here (task_id, correlation_id, root_requester)
```

Cedar's `principal` is always the **executing agent**, never the delegating
human — unchanged from ADR-001 decision #3's existing rule for
workload-executing-on-behalf-of-caller. The human becomes verified
delegation *context*, not a substitute principal.

### 2. Record shape

```json
{
  "delegation_id": "dlg_01J...",
  "version": "1",
  "issuer": {"principal_id": "mona.commercial", "principal_type": "Human"},
  "delegate": {"principal_id": "agent.commercial-normalization", "principal_type": "Agent"},
  "scope": {
    "actions": ["route-cost.normalize", "route.recommend"],
    "resources": [{"type": "RFQ", "id": "rfq-123"}],
    "skills": ["normalize-route-cost"]
  },
  "constraints": {
    "not_before": "2026-07-26T12:00:00Z",
    "expires_at": "2026-07-26T14:00:00Z",
    "max_delegation_depth": 0
  },
  "context": {"purpose": "Prepare commercial recommendation", "correlation_id": "..."},
  "issued_at": "2026-07-26T12:00:00Z",
  "signature": {"alg": "ES256", "kid": "...", "value": "..."}
}
```

`issuer.principal_id`/`delegate.principal_id` are canonical ids (M7 item 1's
`preferred_username`-derived form), never raw IdP `sub`. `scope.resources`
supports action + resource type + resource id from day one — not
action-only — but does not invent a policy language: Cedar remains the
policy language; scope only narrows which Cedar requests a delegation may
accompany.

### 3. Signer: a Delegation Authority, not the human directly

```text
Human authenticates -> Delegation Authority -> signed delegation artifact
```

The human never holds or manages a signing key. A future Mission
Control/control-plane component owns issuance policy, key rotation,
expiry defaults, and revocation state — out of this repo's scope to build
today (see §7), but the record shape and verification contract (§4) are
designed for that component to exist later without a breaking change.

### 4. Verification contract — every PEP receiving delegated authority

Before `context.delegation.*` reaches Cedar, the enforcing library must:

1. verify the signature,
2. verify the signer/key id is trusted,
3. verify `not_before`/`expires_at`,
4. verify `delegate` matches the authenticated executing principal,
5. verify the requested action is within `scope.actions`,
6. verify the requested resource is within `scope.resources`,
7. verify remaining delegation depth,
8. check revocation state when required,
9. only then pass verified facts to Cedar:

```text
context.delegation.verified = true
context.delegation.issuer = Human::"mona.commercial"
context.delegation.id = "dlg_01J..."
```

An unsigned or unverifiable `delegated_by` string, as it exists today,
**must never** be treated as step 9's output — that remains audit-only
provenance, explicitly (existing `AuthorizedContext.delegated_by` docstring,
unchanged by this ADR).

### 5. Scope intersection — delegation narrows, never grants

> Delegation can reduce authority, never create authority the delegate does
> not already independently possess.

```text
effective authority = agent's own Cedar authority ∩ delegation scope ∩ live resource/business constraints
```

A human's €1,000,000 approval limit does not make an agent prohibited from
`quote.approve` (`agents/catalog.yaml`'s `prohibited_actions`) able to
approve anything. Delegation never defeats `prohibited_actions`,
`can_call`, MCP access, or a Cedar `forbid` — those stay unconditional,
exactly as `forbid-delegation-outside-scope` already establishes for the
agent-to-agent case.

### 6. A2A propagation: `max_delegation_depth = 0` by default

For `Human -> Agent A -> Agent B`, Agent A does **not** forward the
original delegation as unrestricted authority for Agent B by default.
Agent A invokes B using A's own already-existing `can_call`/Cedar
authority; the original human delegation rides along as provenance/
accountability only, unless a later, explicit redelegation is issued:

```text
Delegation A: Human -> Agent A
Delegation B: Agent A -> Agent B, parent_delegation_id = Delegation A
```

where the issuing authority for B must verify `scope(B) ⊆ scope(A)` and
decrement remaining depth. Chains are immutable linked grants
(`delegation_id`/`parent_delegation_id`), never a mutable array inside one
token. **Redelegation is explicitly out of scope for this repo's first
implementation** (§7) — the default-zero-depth case is the only one built.

### 7. Showcase implementation scope — deliberately narrow

This ADR authorizes the full model above as the target design. The first
real implementation, when built, is scoped to exactly:

```text
Human -> Agent, single delegation, short expiry, specific actions,
specific RFQ/Quote resource, max depth = 0, control-plane signature,
PEP verification, Cedar context, audit record, revocation lookup
```

No recursive agent-to-agent redelegation. A2A agents keep using their
existing `can_call` graph for agent-to-agent authority — human delegation
establishes accountability and bounded business authority for the entry
hop, it does not replace or wrap the agent authorization graph M3.5–M6b
already built. A minimal Delegation Authority (issuance + revocation
lookup) is new scope, not yet assigned to a milestone — building it is
deferred, this ADR only fixes the shape it must produce and the contract
every PEP must verify against.

### 8. Revocation and fail-closed semantics

`delegation_id` + `expires_at` are sufficient for a showcase: short-lived
grants plus an explicit revocation lookup (`active`/`revoked`/`expired`,
served by whatever holds delegation state) rather than a cached-revocation
optimization, which is a later concern, not a first-pass one. Verification
failure semantics are fixed now, deliberately the opposite of M5.9's
observability posture (which correctly fails *open* — telemetry must never
gate business execution):

```text
cannot verify a required delegation -> no delegated authority (fail closed)
```

never

```text
verification service unavailable -> trust the metadata anyway
```

### 9. Correlation is not authority

`correlation_id`/`root_requester`/`parent_task_id` stay outside the signed
authorization semantics — provenance, not authority, matching the existing
posture `AuthorizedContext.delegated_by`'s docstring already established
for the pre-ADR-003 world. A `correlation_id` MAY be included inside a
signed delegation artifact for evidence-integrity purposes, but Cedar must
never derive an authorization decision from it.

## Invariant

> Delegation conveys bounded authority from one authenticated principal to
> another; it never changes the authenticated identity of the executing
> principal, and never expands the delegate's independently authorized
> capabilities.

## Consequences

- New Cedar context shape (`context.delegation.verified`/`.issuer`/`.id`)
  will be added to `business/actions.yaml`'s per-action `context:` blocks
  for any action that becomes delegation-aware — additive, optional,
  same posture ADR-001 already used for `executing_workload`/`tool`.
- `rfq_common.pep`'s existing `delegated_by`/`AuthorizedContext` audit
  field is unchanged by this ADR — it remains provenance-only until a
  caller actually constructs and verifies a real delegation artifact per
  §4; this ADR does not retroactively upgrade its authorization weight.
- No Delegation Authority / Mission Control component exists in this repo
  yet — this ADR fixes the contract it must implement, not a working
  implementation. Building §4's verification library and §7's minimal
  issuance/revocation surface is new, not-yet-assigned scope.
- Redelegation (§6's `parent_delegation_id` chains) is designed but
  explicitly not built in the first pass — `max_delegation_depth = 0` is
  the only case any real code needs to handle initially.
