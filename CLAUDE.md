# Repo-wide guidance

## Showcase realism, right-first-time

This repo's value is credibility: it's shown to people judging whether it
understands the domain it claims to model (logistics, identity,
authorization, pricing — whichever system is in view). A result that looks
absurd to anyone with domain knowledge — a trans-continental shipment
costing less than a coffee, a permission model that can't explain who
granted what, an FX conversion silently facing the wrong direction — is not
a minor detail to patch after it's noticed live. It's the showcase failing
its one job. Domain mechanics (units, money, weight/volume, provenance,
validity windows, state transitions) must be modeled to match real-world
practice on the first pass, not stubbed "plausible enough for now" and
corrected reactively.

Distinguish two different things that get conflated under "don't invent":

- **Structure/mechanics** — types, invariants, and representations that
  encode facts already true about the domain (a rate's currency determines
  major-vs-minor units; a chargeable weight is the greater of gross and
  volumetric; a decision needs a reason when it can't be evaluated). Build
  these unconditionally, without waiting for sign-off — withholding them
  isn't caution, it's leaving the door open for exactly the kind of silent,
  undetected bug that erodes a showcase's credibility.
- **Policy/business content** — the actual numbers, thresholds, and
  formulas nobody has decided yet (a margin percentage, a rounding band, an
  approval limit). These genuinely need explicit authorization before being
  invented, and must stay clearly labeled as synthetic/demo when authorized
  without being a real decided business policy.

Getting this distinction right is what lets the showcase move fast on
mechanics while staying honest about what's real business logic versus
what's illustrative.
