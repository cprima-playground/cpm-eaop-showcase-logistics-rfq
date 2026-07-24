# ADR-005 — Human-approval boundaries

**Status:** accepted.
**Context:** the repricing process is long-running and human-in-the-loop. Where the
human decision *lives* determines whether agents stay non-authoritative and whether
the process is cleanly resumable.

## Decision

The human decision **is a `Quote.status` transition in the quote system of record
(QMS/CRM)**: `approval_required → approved | rejected | revise`.

- The approval task / workflow MCP is a **mechanism only** — it surfaces the decision
  to a human and triggers resumption; it does **not** own the decision.
- The process **resumes on observing the status change** (`revise` → re-plan), not on
  a workflow callback. No agent holds authoritative state across the wait.
- The human sees a **decision-evidence package** — baseline vs recommended vs
  alternative lane · FX source/timestamp · converted costs · margin impact · transit
  delta · **structured `triggered_thresholds`** · agent recommendation.
- A manager may approve a deviation **within a delegated commercial limit** (policy D6).

## Rationale

- A status transition in the SoR is durable, auditable, and survives instance
  replacement (supports Cloud Run + determinism).
- Keeps agents non-authoritative (ADR-002) and the loop genuinely resumable (scenario 03).

## Alternatives

- **Workflow system owns the decision** — rejected: splits truth from the quote;
  agents/UI would reconcile two stores.
- **Agent auto-applies the decision** — rejected: bypasses the human + the delegated limit.

## Consequences

- QMS is the only mandatory frontend (the approval UI writes `Quote.status`).
- Obligations (commercial approval · notify · reviews) attach to the permits; the PEP
  enforces them; the human transition is the gate.
- Scenario 03 exercises the `approval_required → revise → … → approved` trail.
