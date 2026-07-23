# Running the showcase deterministically

A live demo must be **reproducible**: the same scenario pack always yields the same
decisions. Restarting the mocks is the blunt tool; the real determinism comes from a
**pinned clock**, a **fixed seed**, and an **idempotent apply**.

## Prefer `scenario apply` over restart

```text
scenario apply <pack-id>
  1. reset every backend to baseline      (reload jsonl fixtures, in-memory)
  2. apply the pack's ABSOLUTE state       (overlay overrides · FX · rates · initial Quote.status)
  3. reload the PDP's dynamic entities      (re-PUT RFQ/Quote/RouteOption; do NOT restart cedar-agent)
  4. stamp a run_id on the run
```

Absolute, not delta → re-applying is safe (no drift). This is faster than a restart
and needs no redeploy.

## Two tiers

| Tier | Mechanism | Use |
| --- | --- | --- |
| **Cheap** (live demo) | `POST /admin/reset?pack=<id>` per backend + `scenario apply` | between runs |
| **Hard** (CI / clean-room) | container restart → baseline → `scenario apply` | guaranteed clean |

## The three determinism enablers (restart alone gives you none of these)

1. **Pin the clock.** `fx_age_seconds` and the freshness window (policies D1/D2) are
   `now − observed_at`. On wall-clock the same fixture drifts and D1 can flip
   allow↔deny between demos. Inject **`NOW`** per scenario (frozen, like cpm-eaop
   golden fixtures at `2026-01-01`). Pack `observed_at` + pinned `NOW` = a fixed
   `fx_age_seconds`.
2. **Fixed seed.** The ±5% cost noise uses seed=42 (`systems/rate/fixtures/cost-model.md`)
   → byte-stable rates.
3. **Reload the PDP, don't wipe it.** `cedar-agent` is in-memory. A pack changes
   dynamic entities; re-PUT them via the bootstrap/`cedar-load` path. **Never restart
   the cedar container per run** — that drops schema+policies (cpm-eaop rule); re-PUT
   is faster and complete.

## Auditability

Stamp a **`run_id`** (and a correlation id) on every event + decision, so a re-run is
distinguishable and the decision trail matches the scenario's `then.authorization`
block. Mirrors cpm-eaop's `decision_id` per decision.

## Determinism checklist per run

- [ ] `NOW` pinned (matches the pack's FX `observed_at` offset)
- [ ] seed fixed (42)
- [ ] backends reset to baseline, pack applied (absolute)
- [ ] PDP dynamic entities re-PUT (schema+policies untouched)
- [ ] `run_id` stamped
- [ ] result equals the scenario `.yaml` `then` block
