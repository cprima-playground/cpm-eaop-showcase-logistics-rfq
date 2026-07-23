# ADR-001 — Agentic RFQ scope

**Status:** accepted.
**Context:** the RFQ domain is large (intake → sourcing → pricing → booking). A
showcase must be narrow enough to spike, rich enough to demonstrate real agentic
governance.

## Decision

Scope the showcase to the **repricing subprocess** — *Cross-Currency Lane Repricing
and Approval* — triggered by a **business event** (FX change or route unavailable),
**not** RFQ intake. The RFQ already exists; the process wakes because the business
world changed.

## Rationale

- Event-driven, multi-agent, human-in-the-loop is a far more compelling story than
  "an agent receives an RFQ."
- One realistic event (flagship scenario 04) exercises routing, MCP, an external API,
  Cedar, multiple agents, and human review at once.
- Narrow enough for a first spike; the same architecture later covers other events.

## Alternatives

- **RFQ intake first** — rejected: mostly extraction/validation, weak governance story.
- **Whole RFQ lifecycle** — rejected: too broad for a spike.

## Consequences

- Deliverable is a **decision package** (business → actions → identity → data →
  interfaces → agents → Cedar → scenario → spike), not a product.
- `business/process.md`, scenarios 01–04, and `spikes/repricing/` realize this scope.
- Route-unavailable + FX-change reuse one architecture (ADR-003/004).
