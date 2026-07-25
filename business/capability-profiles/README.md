# Capability profiles — schema

Not a job description. An **enterprise capability profile**: the
reusable derivation chain from a real job title down to what a system
(and an agent) can mechanically do.

```text
Job Title
    |
Responsibilities
    |
Business Decisions
    |
Business Capabilities
    |
Systems of Record
    |
API
    |
MCP Tool
    |
Cedar Action
    |
Agent
```

## Process

Per user decision (this session): **one golden template first**
(`commercial-pricing-specialist.md`), reviewed, before applying the
schema to the other 4 researched titles. Order after review:
Transport Planner → Pricing Manager → Carrier Procurement Specialist →
Regional Commercial Director — deliberately specialist-roles-first,
manager-roles-last, since a manager's profile is largely governance
over specialists' outputs and reads as "almost obvious" once the
specialist profiles exist.

## Schema (12 sections, in this order)

1. **Mission** — one sentence, outcome not activity.
2. **Primary systems** — Systems of Record this role reads/writes,
   named per `systems/systems-of-record.yaml`'s canonical system ids.
3. **Consumes** — concrete inputs (named business objects/entities),
   with the upstream role/system that produces each.
4. **Produces** — concrete outputs, with the downstream role/system
   that consumes each.
5. **Decisions** — the business decisions this role actually makes,
   cross-referenced to `business/decisions.md`'s decision IDs where one
   exists. If none exists yet, say so plainly rather than inventing one.
6. **Business rules** — the concrete thresholds/policies this role
   operates under, cited to `authorization/policies.cedar`'s `@id`s.
7. **KPIs** — how the role's performance is actually measured in the
   industry (research-sourced). Flag explicitly if nothing in this
   showcase computes them today — a KPI listed here is not a claim that
   it's implemented.
8. **Authority** — what this role can approve/submit/override
   unilaterally, and the hard boundary (cite the Cedar `forbid` rule)
   where one exists.
9. **Reports to / Manages** — from `identity/actors.yaml`'s `manager`
   field where an actor exists. If the real-world expectation and the
   current directory data disagree, say so — don't silently paper over
   it or silently "fix" it without review.
10. **Collaborates with** — the other roles this one routinely
    exchanges work with (not a reporting line).
11. **Candidate agent responsibilities** — a table mapping explicit
    human responsibility bullets (from `business/job-titles.yaml`'s
    sourced list) to the Cedar action(s)/`owned_actions` that cover
    each. **Required as a table, not a bare action list** — an action
    name alone doesn't show whether the agent covers 1 bullet or 10;
    the "1-3 bullets per agent" pattern the whole showcase is built on
    is only auditable if the mapping is explicit. Include what's
    deliberately *not* covered, not just what is.
12. **Must remain human** — split into three categories, not one list:
    - **Human-accountable** (structural — someone is accountable for
      this regardless of how much surrounding computation automates)
    - **Human-only today** (limited by current agent/tool scope, not
      principle — could plausibly become agent-assisted later)
    - **Potentially agent-assisted** (not currently modeled, no
      principled barrier to building it)

    Don't collapse these — conflating "not automated yet" with "must
    forever remain human" freezes a technical limitation into a
    permanent organizational claim.

See `identity/README.md` for the distinction between `persona`
(Cedar-facing authorization label) and `job_title_id`/`department_id`
(organizational facts) — every profile references the latter, never
infers organization from the former.

## Known refinement for future profiles (not required yet)

`commercial-pricing-specialist.md`'s §5 distinguishes "revise" (a local
pricing adjustment) from what should eventually be its own category:
**"request new operational inputs"** — when the blocker is upstream
(route no longer feasible, rate expired, capacity constrained, FX
unusable), the correct response is a collaboration handoff to Planning
or Carrier Procurement, not a local revision. Not modeled yet; the
Transport Planner profile (§10/Collaborates-with) should make this
handoff explicit from the Planning side, since it's the natural
receiving end of that request.
