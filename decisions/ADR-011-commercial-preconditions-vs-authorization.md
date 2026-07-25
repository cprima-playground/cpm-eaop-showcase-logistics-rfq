# ADR-011 — Commercial preconditions establish feasibility; authorization never substitutes for missing business truth

**Status:** accepted.
**Context:** wiring QMS to actually consult TMS before pricing (closing the
gap where `QuoteVersion.selected_route_id` was accepted verbatim, with zero
check that the route exists or is currently usable) surfaced a question
worth deciding explicitly, not leaving implicit in one `store.py` method:
what kind of check *is* "does TMS say this route is usable," and how does
it relate to Cedar (ADR-004)? The two are easy to conflate — both can
"block an action" — but they answer different questions, and collapsing
them would eventually tempt someone to move this check into a Cedar policy
where it structurally cannot belong (Cedar has no channel to ask TMS
anything; it evaluates attributes it's handed, it doesn't go fetch truth).

## Decision

**Two distinct concerns, never merged:**

1. **Commercial Preconditions** — *the authoritative business facts from
   external Systems of Record that must be successfully resolved before
   QMS may calculate a commercial quotation.* Today: Masterdata, Rate, FX,
   TMS (route executability). Answers: **is this commercially/physically
   real and current?** Enforced in `mock_qms/store.py`'s `price_version()`,
   fail-closed, same discipline each dependency already uses individually
   (`ComposeIncompleteError` if unconfigured, a dependency-specific error —
   `RouteUnavailableError` for TMS — if the fact resolves to "not usable").
   This is plain application code talking to other Systems of Record over
   HTTP. It is not a policy engine's job.

2. **Authorization** (ADR-004, Cedar) — *whether a principal may perform a
   given action on a given resource.* Answers: **is this principal allowed
   to do this?** Cedar evaluates attributes it is handed by the PEP; it has
   no mechanism to independently ask TMS "is this route real," and must
   not be given one — that would smuggle a live external-system query
   into a policy-evaluation path, breaking Cedar's own model (typed
   schema, pure attribute evaluation, `docs/policies/domain-to-cedar-runbook.md`'s
   decision-first method) for a question it isn't shaped to answer.

**Ordering is one-directional and non-substitutable**: Commercial
Preconditions are checked first, at the point QMS attempts to price a
QuoteVersion. Only a QuoteVersion that has cleared them ever reaches an
authorization decision. **Authorization never substitutes for missing
business truth** — a principal being fully permitted to price a
QuoteVersion has no bearing on whether the route in it actually exists or
is currently usable. Cedar permitting the action on a QuoteVersion
referencing a route TMS has flagged `unavailable` would be a bug in the
QMS-to-TMS wiring having been skipped, not a case for Cedar to catch —
Cedar was never the layer positioned to catch it.

**Consistent, generalizing rejection language**: when a Commercial
Precondition fails, the rejected party is named as the **QuoteVersion**,
not the individual System of Record — *"QuoteVersion cannot be priced:
commercial precondition 'route executable' not established for
{route_id} ({status} per TMS)"*. The same shape holds for a future
rate-expired or capacity-unavailable rejection without needing new
wording: precondition name changes, sentence doesn't.

## Rationale

- Keeps Cedar's scope exactly what ADR-004 already committed to —
  authored actions, typed projection, attribute evaluation — and stops a
  plausible-looking shortcut ("just add a Cedar condition that checks
  route status") from quietly handing the PDP a live-data-fetching job it
  was never designed for.
- Matches this repo's existing fail-closed convention for every other
  unresolvable external dependency (`MasterdataUnavailableError`,
  `ComposeIncompleteError`) — Commercial Preconditions aren't a new
  mechanism, they're the existing one, named, now that TMS makes it four
  checks instead of two or three.
- Gives future contributors a concrete test for "does X belong in Cedar or
  in Commercial Preconditions": *is X a fact about whether something is
  real/current (Commercial Precondition), or a fact about who is allowed
  to act on it (Authorization)?* Capacity and embargo checks, when they
  arrive, are the former; a new approval-tier rule is the latter.

## Alternatives

- **Encode route-availability as a Cedar condition/context attribute,
  fetched by the PEP before evaluation** — rejected: this would work
  mechanically (PEP already assembles context), but blurs the boundary
  this ADR exists to state — every future System-of-Record fact would then
  have a live path into Cedar's context assembly, and "is this real"
  questions would end up scattered across both PDP context-building code
  and application code, instead of living in one place (`price_version()`).
- **No explicit distinction — treat it as just another validation step in
  `price_version()`, undocumented as a named concept** — rejected: this is
  what existed before TMS wiring (masterdata/rate/fx checks with no shared
  name). Naming it now, while there are still only four, is cheap; doing
  it after a fifth and sixth precondition arrive without a name is not.

## Consequences

- `mock_qms/store.py`'s `price_version()` docstring states the Commercial
  Preconditions definition verbatim, so the concept is discoverable in
  code, not only in this ADR.
- New Systems-of-Record facts QMS must resolve before pricing (capacity,
  embargo, customer-specific restrictions) are Commercial Preconditions by
  default unless they're actually about permission to act, not about
  whether something exists/is usable — that test is stated above and
  should be applied each time, not re-litigated.
- Cedar policies (`policies.cedar`) must never be authored to encode "is
  route/rate/masterdata fact X currently true" — if a reviewer sees a
  Cedar condition doing that, it's a sign the check belongs in
  `price_version()` instead.
- An audit-event trail for Commercial Precondition rejections
  (`PricingRejected reason=<precondition> source=<SoR>`) is a natural
  future extension of this decision but requires event/audit-log
  infrastructure this codebase doesn't have yet — explicitly deferred, not
  part of this ADR's scope.
