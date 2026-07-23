# Scenario 03 — Approval loop (long-running human-in-the-loop)

Extends scenario 01. The human does not approve the recommendation — they set
`Quote.status = revise` and request a different lane. The process **resumes**: the
Lane agent re-evaluates, normalization reruns, a new recommendation + approval
package is produced. Demonstrates the genuinely long-running, resumable HITL.
Machine companion: `03-approval-loop.yaml`.

## Why this matters

The trigger to resume is a **status change in the quote system of record**, not a
workflow callback the agents own. The agents poll/observe `Quote.status`; a
`revise` transition wakes the loop. Nothing is authoritative in the agents.

## Steps

1. (Scenario 01 result) Route B recommended; `Quote.status = approval_required`;
   human review package delivered.
2. Human sets **`Quote.status = revise`** in CPQ with a note: *"try to keep the
   contracted Hamburg lane; re-check a cheaper carrier."*
3. Process observes the `revise` status → **Lane agent resumes** (`lane.evaluate`),
   searches again, produces a new option set (e.g. a cheaper Route A carrier).
4. Commercial agent **reruns** normalization on the new options (`route-cost.normalize`).
5. Route agent produces a **new recommendation** (`route.recommend`) — say Route A
   now viable → contracted lane → **D3a** (no obligation), margin ≥ floor.
6. New approval package; `Quote.status = approval_required` again.
7. Human sets **`Quote.status = approved`** → new quote version written; loop ends.

```text
recommend → approval_required → human sets revise → lane agent resumes
→ new option → normalization reruns → new recommendation → approval_required
→ human sets approved → done
```

## Expected authorization decisions (second pass)

| # | action | principal | resource | effect | obligations |
| - | --- | --- | --- | --- | --- |
| — | lane.evaluate | lane-evaluation-agent | RFQ::RFQ-1001 | allow | — |
| D2 | route-cost.normalize | commercial-norm-agent | RouteOption::route-a2 | allow | — |
| D3a | route.recommend (contracted) | route-decision-agent | RFQ::RFQ-1001 | allow | — (contracted, no obligation) |
| D6 | route-deviation.approve | mona.commercial | RouteRecommendation::REC-1001-v3 | allow | — |

## Expected system-of-record changes

- CPQ `Quote.status`: `approval_required → revise → approval_required → approved`
  (each transition is a durable, observable decision point).
- New quote version on final approval.

## Acceptance criteria

A `revise` status transition — not a workflow callback — resumes the process; the
second pass runs the same agents/policies to a fresh approval package; the loop
terminates on `approved`. No agent holds authoritative state across the wait.
