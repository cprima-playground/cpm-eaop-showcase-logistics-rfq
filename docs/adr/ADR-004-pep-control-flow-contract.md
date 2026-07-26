# ADR-004: `rfq_common.pep` control-flow contract

Status: Accepted
Date: 2026-07-25

## Context

The identity/directory foundation is frozen (M1-M3.4, `identity/
README.md`). The next milestone, M4a, builds `rfq_common.pep` — the
distributed enforcement library every MCP server (and later the admin
surface) imports directly (implementation plan decision #1). Before
writing that code, the control-flow contract — what the two entry
points return, and exactly how they fail — needs to be fixed, so M4a's
implementation has a target to match rather than improvising exception
shapes mid-build.

This ADR does not implement M4a. It fixes the contract M4a must
satisfy.

## Decision

Two entry points, not one, with a clear division of responsibility:

```python
def authorize(principal, action, resource, context) -> Decision: ...

def authorize_and_enforce(principal, action, resource, context) -> AuthorizedContext:
    """Raises AuthorizationDenied on deny.
    Raises ObligationEnforcementError when a required obligation cannot
    be satisfied."""
```

- **`authorize`** — thin wrapper over the already-existing
  `rfq_common.pdp.PDPClient.authorize()` (unchanged signature/return
  shape, `AuthorizationDecision`). Returns a decision; never raises for
  a deny — the caller decides what a deny means in their context. This
  is the primitive `rfq_common.pdp.PDPClient.authorize()` already is;
  `rfq_common.pep.authorize` is not a new implementation, just the
  library's public re-export at the layer M6's MCP servers import from
  (they import `rfq_common.pep`, not `rfq_common.pdp` directly — keeps
  every enforcement point going through one library, per decision #1).

- **`authorize_and_enforce`** — the actual enforcement point. Callers
  (an MCP tool handler) call this, not `authorize`, whenever the
  decision itself should gate whether execution proceeds. Three
  outcomes:
  1. **Permit, no obligations** → returns `AuthorizedContext`.
  2. **Permit, with obligations, all satisfiable** → resolves them
     (`authorization/obligations.yaml`, same pattern as
     `PolicyBundle.resolve_obligation_ids`), attaches them to
     `AuthorizedContext`, returns normally.
  3. **Deny** → raises `AuthorizationDenied` (caller doesn't get a
     `Decision` object to inspect-and-ignore — the exception forces a
     stop, matching decision #9's bypass-resistance requirement:
     forgetting to check a boolean return is a real class of bug this
     avoids).
  4. **Permit, but a required obligation can't be satisfied** (e.g. the
     obligation names a downstream action that itself isn't available,
     or the obligation resolver has no mapping for an obligation id
     Cedar returned) → raises `ObligationEnforcementError`, distinct
     from `AuthorizationDenied`. Cedar said permit; the *enforcement*
     of what permit requires failed — a different failure category,
     and callers should not treat it as "denied," since retrying after
     fixing the obligation-resolution gap (not the authorization
     request) is the correct remediation.

### Shapes

```python
class AuthorizedContext:
    principal: CanonicalPrincipal   # from decision #2's resolve_principal
    decision: Decision              # the underlying PDPClient decision, kept for audit
    obligations: list[ResolvedObligation]  # empty if none

class AuthorizationDenied(Exception):
    decision: Decision              # carries determining_policies for audit/error messages

class ObligationEnforcementError(Exception):
    obligation_id: str
    reason: str
```

`Decision`/`CanonicalPrincipal`/`ResolvedObligation` are not new types —
`Decision` is `rfq_common.pdp.AuthorizationDecision` (existing);
`CanonicalPrincipal` is M3.4's already-built `src/rfq_common/
rfq_common/pep/resolve.py` output; `ResolvedObligation` is whatever
shape `PolicyBundle.resolve_obligation_ids` already returns, reused not
redesigned.

### Operational caution for M4a's implementation (not a code change now)

The two existing `has_role()` 403-gates (`mock_qms/api.py:128`,
`ops_dashboard/api.py:345`, `identity/README.md`'s "roles claims"
section) are **not** removed in one pass when `authorize_and_enforce`
lands. Migrate operation-by-operation: for each gate, add the Cedar-
backed check alongside it, prove equivalent-or-stricter behavior with a
test, *then* remove the `has_role()` gate for that specific operation.
Removing all of them up front risks a window where an operation has
neither a working UI-role gate nor a wired-up Cedar check — a real
enforcement gap, not a hypothetical one, given decision #9's bypass-
resistance requirement is exactly what this migration must not
accidentally violate mid-migration.

## Naming correction (review round 3): this is not A2A

`test_pep_delegation_checkpoint.py` proves an **agent-to-MCP operation
carrying claimed human-delegation context** — `route-decision-agent`
authenticating directly to `approval-mcp` as an OAuth-credentialed MCP
client, per ADR-001 decision #3's already-established pattern. It does
**not** prove A2A (agent-to-agent): no agent discovery, Agent Card,
`SendMessage`/task lifecycle, A2A server endpoint, agent-to-agent JWT
audience binding, or one agent invoking another agent (rather than an
MCP tool) is exercised anywhere in this repo. Cedar's `AgentPrincipal`
type and the `can_call`/`agent.delegate` machinery (M3.5) describe *what
kind of principal* is being authorized and *Cedar-readiness* for a
future A2A authorization boundary — neither is evidence that the A2A
protocol itself is in use. A real A2A path would introduce a genuinely
different boundary (Agent A → A2A → Agent B → MCP → Cedar), needing
Cedar to distinguish *requesting* agent from *executing* agent as two
separate facts — not modeled here, correctly out of scope for M4a.

Corrected terminology, used from here on: **"agent-to-MCP operation with
claimed human delegation context,"** not "delegated A2A operation." The
milestone below is still called "the delegation checkpoint" informally
(delegation of human accountability *context*, via `delegated_by`) — not
delegation *of the interaction itself* to another agent.

## Addendum: second checkpoint review, round 2

The checkpoint (`test_pep_delegation_checkpoint.py`) was reviewed and
found **partially passing** — accepted as "one-operation delegation
behavior proven," not yet "reusable delegated-enforcement primitive."
Four gaps addressed:

1. **`delegated_by` is a claimed delegator, not a verified one.**
   `authorize_and_enforce` performs no resolution/signature/delegation-
   record check on it — any caller constructing `context` can assert
   anything. Documented explicitly in `enforce.py`'s `AuthorizedContext`
   docstring (not renamed publicly, per review's own guidance against
   churn); `audit_record()`'s key renamed `accountable_principal` →
   `claimed_delegator` so the audit trail doesn't overstate what's
   established. `test_delegated_by_claim_carries_no_authorization_weight`
   proves the gap concretely: Cedar's decision is identical whether the
   named delegator is real or fabricated. Closing this for real is
   ADR-003's job (delegation-establishment path), not done here.
2. **Delegation scope was action-specific** (`route.recommend` only), no
   general invariant. `test_delegation_scope_coverage.py` enforces the
   convention structurally: any action declaring `delegated_by` in its
   context must have a matching `forbid`-with-`delegatable_actions`
   policy, or the test fails — closes the "new delegated action, forgot
   the forbid" failure mode the review named.
3. **`approval.request` had reappeared** — Finding 2's original fix
   removed agent *ownership* (`agents/catalog.yaml`) but left the action
   *definition* in `business/actions.yaml`, incomplete execution of an
   already-frozen decision, not a new reversal. Removed for real;
   `test_frozen_action_vocabulary.py` guards against recurrence.
4. **Artifact-boundary gap**: the `has`-guard limitation on
   `forbid-delegation-outside-scope` was documented but only tested at
   generator-source level. `test_every_agent_entity_has_delegatable_actions_never_absent`
   (`tools/identity/tests/test_gen_cedar_entities.py`) now checks the
   generated entity output directly.

## Consequences

- M4a's task list (`resolve_principal`, `authorize_and_enforce`) now
  has a fixed target signature and exception contract to implement
  against, not to invent while coding.
- MCP servers (M6) written against `authorize_and_enforce` get
  bypass-resistance "for free" — a forgotten deny-check is a Python
  exception propagating up (likely a 5xx or unhandled error), not a
  silently-ignored `False`.
- `ObligationEnforcementError` as a distinct exception type means M6's
  error handling can't collapse "you're not allowed" and "you're
  allowed but we couldn't do what that requires" into the same HTTP
  status without a deliberate choice.
- The `has_role()` migration caution is binding on however M4a's
  rollout is sequenced later — not enforced by a test today (no
  `authorize_and_enforce` implementation exists yet to test), but
  recorded so the rollout PR/commits can be reviewed against it.
