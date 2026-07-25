# Identity — schema notes

`identity/actors.yaml` + `identity/groups.yaml`: implementation-scoped
principals and group membership, validated by `tools/identity/
validator.py`. See `business/capability-profiles/README.md` for how
this connects to the organizational model (departments, job titles,
responsibilities).

## `persona` is not a job title or department

Formalizing this centrally because it's easy to assume otherwise:

> **`persona` is an architectural authorization label, not an
> organizational job title or department.**

It names which Cedar-facing authority tier / group an actor belongs to
(`CommercialManager` = has approval authority via the `rfq-commercial-*`
group; `PricingManager` = individual-contributor quote-building track
via `rfq-pricing-*` — yes, the labels are historically swapped relative
to what they sound like; see `job_title_id` for the real-world name).

`job_title_id` (→ `business/job-titles.yaml`) and `department_id` (→
`business/departments.yaml`) are the organizational facts — what a
logistics professional would recognize on an org chart. `persona`
predates that model and is kept unchanged for backward compatibility
(existing Cedar-entity-uid tests depend on the actor `id`s it's attached
to) — do not infer department, job family, or org placement from
`persona`. Two fields can and do diverge on the same actor
(`mona.commercial`: `persona: CommercialManager`,
`job_title_id: pricing-manager`, `department_id: commercial`) — that's
expected, not a bug to reconcile.

## Validated invariants

`tools/identity/validator.py` enforces, beyond basic shape:

- No orphaned `member_of` (every group referenced exists in
  `groups.yaml`).
- No duplicate canonical `id`.
- `manager` references a known actor id.
- `job_title_id`/`department_id`, when set, resolve against
  `business/job-titles.yaml`/`departments.yaml`.
- **Management-chain enforcement**: if a `job_title_id` declares
  `reports_to_job_title_id`, an actor with that title must report to a
  manager holding *that* title — skipping a declared management layer
  (e.g. a specialist reporting straight to a director) is a validation
  error, not just a style preference.

Provider-specific fields (`keycloak_client` and equivalents) are never
identity facts — see `identity/actors.yaml`'s header comment and
`business/capability-profiles/README.md`'s derivation chain for where
those belong instead (provider projection config, introduced later in
the implementation plan's M3.5).
