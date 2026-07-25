# Abbreviation inventory — R1-R6 / D1-D19(+ab)

Discovery only, not a rename. `R1`-`R6` (business rule ids,
`business/qms-pricing-rules.md`) and `D1`-`D19` plus `D3a`/`D3b`/`D4a`/`D4b`
(authorization decision ids, `business/decisions.md`) predate this session
— they were an established project convention before any of today's work —
but this session extended their use further (new `RuleResult`s in
`mock_qms/pricing_policy.py`/`store.py`) without ever stopping to ask
whether the convention itself should continue. This file is that pause:
every real occurrence, so renaming (if wanted) is a scoped, deliberate
decision, not a silent continuation.

Generated via `grep -rn` across every `.py`/`.md`/`.yaml`/`.yml`/`.cedar`
file, excluding `.venv`/`__pycache__`/`.git`. Spot-checked for false
positives (e.g. a stray "D4" that isn't the decision id) — none found in
this pass, but a full rename would still warrant re-checking each hit by
hand, not a blind find/replace.

## Legend — what each id actually means

### Rule ids (R1-R6) — `business/qms-pricing-rules.md`

| Id | Meaning |
| --- | --- |
| R1 | Margin floor — `margin_pct_x10 < margin_floor` → commercial approval (D5) |
| R2 | FX variance since prior quote — `> 2.0%` → D4b forbids auto-replace, D4a permits human recalc |
| R3 | Route cost variance vs. baseline — `> 8.0%` → D8 permit + review obligation |
| R4 | Transit time variance — `> 3 days` → D9 permit + review obligation |
| R5 | Non-contracted lane — D3b permit + review obligation (D3a if contracted, no obligation) |
| R6 | Quote value vs. delegated approval limit — D6 (commercial manager may approve within limit) |

### Decision ids (D1-D19) — `business/decisions.md`

| Id | Question | Status |
| --- | --- | --- |
| D1 | May the commercial agent read the FX rate if fresh enough? | modeled |
| D2 | May the commercial agent normalize a route cost with a referenced FX snapshot? | modeled |
| D3 / D3a / D3b | May the decision agent recommend a non-contracted lane? (D3a=contracted/no obligation, D3b=non-contracted/obligation) | modeled |
| D4 / D4a / D4b | Must automatic quote replacement be blocked when FX moved >2%? (D4a=human recalc permit+notify, D4b=forbid auto-replace) | modeled |
| D5 | May a below-floor margin quote be proposed at all? | modeled |
| D6 | May a commercial manager approve a route deviation within their limit? | modeled |
| D7 | Inactive principals must not perform any controlled action (cross-cutting forbid) | enforced |
| D8 | May the decision agent recommend a route whose cost exceeds baseline by >8%? | modeled |
| D9 | May the decision agent recommend a route adding >3 transit days? | modeled |
| D10 | May an active agent check route capacity? (read-only) | enforced |
| D11 | May an active agent evaluate lane options for an RFQ? (read-only) | enforced |
| D12 | May a quote be submitted when FX is quiet and margin is at/above floor? (baseline permit) | modeled |
| D13 | May the lane agent read this RFQ? | proposed |
| D14 | May the lane agent read this carrier/customer-specific rate? | proposed |
| D15 | May the commercial agent read the underlying buy rate? | proposed |
| D16 | May the commercial agent create a new quote version from this recommendation? | proposed |
| D17 | May the commercial agent supersede this quote version? | proposed |
| D18 | May this principal expose underlying buy-cost details? | proposed |
| D19 | (candidate only — no decisions.md row yet) The human-in-the-loop decision on a quote version (approve/reject/revise) | not modeled |

## Occurrence counts

**Rule ids:** R1 (29) · R2 (17) · R3 (9) · R4 (6) · R5 (10) · R6 (12)

**Decision ids:** D1 (30) · D2 (19) · D3 (2) · D3a (6) · D3b (20) · D4 (15) ·
D4a (11) · D4b (24) · D5 (21) · D6 (25) · D7 (6) · D8 (13) · D9 (19) ·
D10 (9) · D11 (9) · D12 (16) · D13 (3) · D14 (5) · D15 (11) · D16 (21) ·
D17 (11) · D18 (11) · D19 (2)

## Every file with at least one occurrence

**Documentation / business / authorization (source of truth for the ids):**
- `business/decisions.md` — the D1-D19 canonical table
- `business/qms-pricing-rules.md` — the R1-R6 canonical table
- `business/domain-model.yaml`, `business/glossary.md`
- `authorization/policies.cedar` — every D-id's actual Cedar policy
- `authorization/governance-policies.md`
- `decisions/ADR-002-sor-boundaries.md`, `ADR-005-human-approval-boundaries.md`, `ADR-006-tech-stack.md`, `decisions/README.md`
- `build-plan.md`, `KNOWN-ISSUES.md`, `README.md`, `RUNNING.md`, `TODO.md`
- `systems/data-provenance.md`
- `traceability.yaml`

**Scenarios / fixtures (demo data referencing specific decisions):**
- `scenarios/01-fx-flips-lane.md` + `.yaml`
- `scenarios/02-route-unavailable.md` + `.yaml`
- `scenarios/03-approval-loop.md` + `.yaml`
- `scenarios/04-combined-route-fx-shock.md` + `.yaml`
- `fixtures/normalized-options.yaml`
- `fixtures/scenario-packs/README.md`, `cny-eur-threshold.yaml`, `combined-route-and-fx-shock.yaml`, `hamburg-port-closure.yaml`, `rail-capacity-exhausted.yaml`
- `interfaces/api/README.md`
- `infra/compose.sketch.yaml`

**Spikes:**
- `spikes/repricing/README.md`, `spikes/repricing/policy-evaluation/README.md`
- `spikes/repricing/policy-evaluation/test_scenarios.py`

**Application code (real, running):**
- `src/rfq_common/rfq_common/clock.py` — comment referencing D1/D2 (FX freshness)
- `src/rfq_common/rfq_common/models/qms.py` — comments referencing D15/D18/D16/D17
- `src/rfq_common/rfq_common/models/rate.py` — comment referencing D14/D15
- `src/rfq_common/tests/test_pdp_integration.py` — D6 test
- `src/mock-fx/mock_fx/api.py`, `src/mock-fx/mock_fx/generator.py` (D4 threshold), `src/mock-fx/tests/test_store.py`
- `src/mock-tms/tests/test_store.py`
- `src/mock-qms/mock_qms/api.py` — every route's `x-domain-action`/`x-gap` comments (D4/D5/D6/D12/D13/D14/D15/D16/D17/D18/D19-candidate)
- `src/mock-qms/mock_qms/store.py` — **this session** (R1/R2 real evaluation, R3-R5 not_evaluated)
- `src/mock-qms/mock_qms/pricing_policy.py` — **this session** (new file, R1/D5/D6 references)
- `src/mock-qms/mock_qms/cli.py` — **this session**
- `src/mock-qms/tests/test_pricing.py` — **this session**
- `src/ops-dashboard/README.md`, `src/rfq_common/README.md`, `src/mock-fx/README.md`

**Fixture data:**
- `systems/qms/fixtures/quotes.yaml`

## What this session added

`mock_qms/pricing_policy.py` and the `RuleResult`s now written by
`mock_qms/store.py`'s `price_version()` continue the R-id convention
(`rule_id="R1"` etc.) and reference D5/D6/D12 in prose — consistent with
the pre-existing pattern, not a new one, but still a real extension worth
flagging: every new `RuleResult.reason` string and pricing-policy docstring
uses these ids too.

## Not done here

No renaming, no opinion on whether Rx/Dx should become descriptive names
(e.g. `margin-floor` instead of `R1`, `commercial-manager-approve-within-limit`
instead of `D6`). That would touch every file above plus the actual Cedar
policy ids in `authorization/policies.cedar` (which downstream tooling may
already depend on) — a real, larger, separate decision.
