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

## Keycloak `roles` claims are not canonical authorization facts

Hard rule, stated before M4a builds anything that resolves a token into
an authorization decision: **`roles` claims are not canonical
authorization facts unless an explicit projection contract says
otherwise.** `qms-web`'s client roles (`reader`/`commercial-manager`/
`pricing-manager`/`administrator`, `infra/keycloak/terraform/
keycloak-qms.tf`) are application-local UI entitlement — "what does this
QMS session's UI show" — not what Cedar authorizes on. Cedar authorizes
on canonical principal id + **group** membership
(`Agentic::Group::"rfq-commercial-emea"`), never a role name.

`src/rfq_common/rfq_common/identity.py`'s `Principal.roles`/`has_role()`
carry a HARD RULE comment for exactly this reason: `resolve_principal()`
is the natural place someone building M4a's principal resolver would
reach for a convenient `roles` claim and accidentally reintroduce
Keycloak's UI entitlement model as an authorization model — undoing the
separation this project deliberately built. If a future case genuinely
needs a role-shaped fact in Cedar, it needs its own named projection
contract (like `job_title_id`/`department_id`'s), not silent reuse of
this claim.

Two existing `has_role()` call sites (`mock_qms/api.py:128`,
`ops_dashboard/api.py:345`) already self-document as interim/UI-gating
(`raise HTTPException(403)` on a missing Keycloak role) — the known
pre-Cedar access-control placeholder the "Business-logic baseline"
section's maturity statement means by "PDP authorization: not yet
demonstrated." **M4a's `rfq_common.pep` replaces these, it does not
extend them** — don't add a third `has_role()` gate anywhere, and don't
carry the pattern into the PEP itself.

## Machine credentials are a runtime concern, not an identity fact

Layering, made explicit after M3.3's live Entra export showed 7
generated `azuread_application_password` resources, each with an
expiration date:

```text
Canonical machine principal   (identity/actors.yaml: workload.*/agent.*)
        |
provider application/client   (Keycloak client / Entra app registration --
        |                       tools/identity/gen_{keycloak,entra}.py)
        |
credential                    (client secret -- Terraform-managed,
        |                       never read by any generator)
        |
expiration / rotation         (a provider/runtime lifecycle event)
```

**Identity parity (M3.4) does not imply credential-lifecycle parity** —
proving both IdPs agree on *who* a machine principal is says nothing
about *when its secret expires* or *how it rotates*, and the two are
deliberately decoupled: `canonical_id`, `can_call`, the Cedar entity
data, and the provider `client_id`/`display_name` must never change as
a consequence of rotating a credential. Enforced, not just stated —
`tools/identity/tests/test_credential_lifecycle_independence.py` proves
no generator output depends on or contains any secret/credential value,
so a routine secret rotation later can't accidentally become an
identity event. No credential-management subsystem exists yet
(rotation itself isn't automated — `end_date` is a fixed placeholder in
`infra/entra/main.tf` today); this only guarantees rotation, whenever
it's built, can't corrupt identity.
