# ADR-002 — System-of-record boundaries

**Status:** accepted.
**Context:** a logistics RFQ has **no single system of record** — truth is fragmented
across CRM, TMS, Rate, QMS, FX, and Workflow. Agents must not become shadow stores.

## Decision

- Every business object has **exactly one authoritative owner** (`systems/systems-of-record.yaml`).
- **Agents carry snapshots + identifiers, never authoritative state.** They read/write
  via the owning system, they do not own the object.
- The **human decision is a `Quote.status` transition in the quote SoR (QMS/CRM)** —
  not a record owned by the workflow system (ADR-005).
- Every policy-relevant fact declares source · freshness · fail-behavior (`systems/data-provenance.md`);
  default failure is **deny** (fail closed).

## Rationale

- Mirrors real logistics: an orchestration/agentic layer **reconciles** fragmented
  sources, it does not replace them.
- Non-authoritative agents are safe to restart/replace (supports determinism +
  Cloud Run instance replacement).

## Alternatives

- **Agent owns the RFQ/Quote** — rejected: agents would become an unaudited SoR.
- **One monolithic SoR** — rejected: false to the domain.

## Consequences

- `systems/<system>/` folders own each system's contract + fixtures + mock spec.
- Freshness is a policy input (FX window → D1/D2 deny), not a nicety.
- Reconciliation logic lives in agents; authority stays in the SoRs.
