# ADR-004 — Authorization model

**Status:** accepted.
**Context:** the showcase must govern agent actions with a real external policy
engine, reusing the cpm-eaop control-plane conventions so the two stay consistent.

## Decision

Use **Cedar as an external PDP** (the `permitio/cedar-agent` sidecar), mirroring
cpm-eaop `data/policies/`:

- **Authored actions** (`authorization/actions.yaml` → business/actions) — dotted,
  namespaced, `principals`/`resources`/`context` typed. Never generated.
- **Authorization projection** (`authz-projection.yaml`) as a coupling firewall —
  `namespace: Agentic`; **only `member_of` → `Group` is a parent**, every other
  relation a typed attribute.
- **Generated schema** (`agentic.cedarschema`) from projection + actions — never hand-edited.
- **Policies** (`policies.cedar`) with `@id/@version/@owner/@description` + `@obligations`;
  **`forbid` beats `permit`** (deny-precedence); conditions read resolved attributes.
- **Obligations** resolved **Python-side** (flat payloads) + enforced by a PEP — Cedar
  never sees obligations.
- **Three distinct threshold types → distinct policies** (commercial · FX · lane),
  plus cost/transit — not one tangled rule.

## Rationale

- Typed schema + validate-on-load (Cedar) catches errors the OPA/Rego path wouldn't.
- Decision-first method (`docs/policies/domain-to-cedar-runbook.md`): question →
  actions → projection → schema → policies → tests.
- Deny-precedence + obligation-merge model the threshold surface cleanly (scenario 04).

## Alternatives

- **OPA / Rego** — rejected: no typed schema/validation; cpm-eaop chose Cedar.
- **Authz logic in the agents/HTTP** — rejected: governor must be external (principle #1).

## Consequences

- `rfq_common` carries the PDP client + entity/context assembly (build-plan Phase 1).
- Adding a rule = author actions/projection/policy; regenerate + reload the schema.
- Grants hot-path is an open item (TODO) layered on this decision if adopted.
