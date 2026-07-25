# Personas — offer-to-cash freight forwarding

Derive identities from real logistics work, not from architecture. This
document, plus `business/departments.yaml` and `business/job-titles.yaml`,
is the foundation `identity/actors.yaml` and `identity/groups.yaml` are
grounded in — job titles and responsibility bullets pulled from real job
postings (cited per role), not invented labels. A logistics professional
reading this should recognize their own job.

Order: **person → responsibilities → which responsibilities an agent can
reasonably cover → directory identity.** Not the reverse.

## The organization is business-complete; the implementation isn't

Two different things, kept in two different places, per this session's
directory review:

- **`business/departments.yaml` + `business/job-titles.yaml`**: the
  organization **as it exists** at a real freight forwarder — includes
  departments and titles this showcase doesn't implement yet (Carrier
  Procurement, Operations, Customs & Trade, Finance). The bounded
  implementation catches up to this over time; the org chart doesn't
  shrink to match today's code.
- **`identity/actors.yaml`**: **implementation-scoped**. A human is only
  added when there's a reason — grounding an agent that already exists,
  or (as with Carrier Procurement Specialist below) making the org chart
  recognizable one step ahead of the agent/API/MCP server that would
  eventually automate part of the role. `identity/*.yaml`'s
  `job_title_id`/`department_id` are stable references into the two
  organization files above, not free text — `tools/identity/
  validator.py` cross-checks both resolve.

Sections below marked **Modeled** have a corresponding human in
`identity/actors.yaml`. Sections marked **Org-complete, not yet
implemented** exist in `departments.yaml`/`job-titles.yaml` with no
human in `identity/actors.yaml` yet — real, recognizable roles, named so
the spine is visible, not silently absent.

## Scope note

This repo's implementation currently covers the **repricing subprocess**
slice of offer-to-cash (RFQ → route evaluation → FX/cost normalization
→ quotation → deviation approval).

---

## Regional Commercial Director — **Modeled** (`human.*.director` / `diane.delgado`)

Oversight role, one per region (EMEA/APAC/AMER). Manages both the
Pricing Manager and the Transport Planner in their region.

Responsibilities (org-chart level, no Cedar-policy role today — no
decision in `business/decisions.md` references a director principal):
- Own regional commercial P&L and pricing governance
- Escalation point above a Pricing Manager's approval limit
- Approve pricing policy/discount structure changes for the region
- Represent the region in cross-regional pricing alignment

**Agent-delegable subset:** none currently. Directors sit above every
existing agent's `prohibited_actions` boundary (all three agents
explicitly exclude `route-deviation.approve`) — this is intentional,
matches the offer-to-cash convention that approval authority stays
human, and the plan's decision to keep director facts directory-only
until a concrete policy needs them.

Sources (Pricing Manager tier, closest attested title for regional
pricing oversight — no distinct "Director" posting found, this level
sits above it): [ISS Global Forwarding Pricing Manager](https://iss-globalforwarding.com/jobs/pricing-manager-malaysia/)

---

## Pricing Manager — **Modeled** (`mona.commercial` + 2 new)

Group: `rfq-commercial-*` (the approval-bearing group — Cedar policy
`manager-may-approve-within-limit` grants this group deviation-approval
authority within an EUR 10,000 limit, unchanged across regions per this
session's decision: real, not varied per-region, matches that the
underlying policy doesn't vary by region either).

Real responsibilities (from postings for "Pricing Manager" /
"Commercial Manager" at freight forwarders):
- Develop/implement pricing strategies for profitability and competitiveness
- Lead pricing governance: standardized practices, discounting policy, approval protocols
- Build rate approval structures and escalation protocols
- Conduct profit margin analysis; review pricing strategy for competitiveness
- Negotiate rates/contracts with carriers and vendors
- Lead pricing reviews, internal approvals, proposal pricing milestones

**Agent-delegable subset:** none — `route-deviation.approve` is the
one action this role owns in the current schema, and it's explicitly
excluded from every agent's `owned_actions`
(`agents/catalog.yaml:25,43,60`). This is the real-world pattern: the
approval decision itself stays human; agents recommend, humans approve.

Sources: [ISS Global Forwarding Pricing Manager](https://iss-globalforwarding.com/jobs/pricing-manager-malaysia/), [Indeed Freight Pricing Manager](https://www.indeed.com/q-freight-pricing-manager-jobs.html)

---

## Commercial Pricing Specialist — **Modeled** (`sam.pricing` + 2 new)

Group: `rfq-pricing-*` (individual-contributor quote-building track, no
approval authority).

Real responsibilities (from "Pricing Specialist"/"Pricing Executive"
postings):
- Prepare freight quotations for Air, Sea (FCL/LCL), and Land
- Coordinate with shipping lines, airlines, transporters, overseas agents for competitive rates
- Support sales with timely, accurate pricing for inquiries and tenders
- Maintain/update rate sheets, tariffs, pricing databases
- Analyze market trends and freight rate fluctuations
- Ensure quotations comply with company policy and service capability

**Agent-delegable subset** → `commercial-normalization-agent`
(`agents/catalog.yaml:30-46`): `fx-rate.read`, `route-cost.normalize`,
`quote-price.calculate`, `quote-variance.evaluate`. Maps to "analyze
market trends and freight rate fluctuations" (FX normalization) and
"prepare freight quotations" (price/variance calculation) — 2 of 6
bullets, not the whole job. The specialist still owns "coordinate with
carriers", "maintain rate sheets", and the commercial judgment behind
"ensure quotations comply with policy" — the agent is explicitly
prohibited from `quote.submit-for-approval` when FX moved > 2%
(`agents/catalog.yaml:43`), keeping that judgment human.

Sources: [ZipRecruiter Freight Forwarding Pricing Specialist](https://www.ziprecruiter.com/Jobs/Freight-Forwarding-Pricing-Specialist), [Hellmann SSC Pricing Specialist](https://careers.hellmann.com/en/jobs/ssc-pricing-specialist-seafreightairfreight)

---

## Transport Planner — **Modeled** (3 new: EMEA/APAC/AMER)

Group: `rfq-planning-*` (new, this session — grounds two existing
agents that previously had no corresponding human in the directory).

Real responsibilities (from "Transportation Planner"/"Load Planner"
postings):
- Plan, tender, and route daily shipments to meet cost/service parameters
- Create optimized shipment routes (distance, time, traffic, customer requirements)
- Identify lowest freight cost and best mode to maximize efficiency
- Monitor load status; adjust plans for delays
- Communicate with drivers and carriers
- Analyze carrier trends, identify service issues

**Agent-delegable subset** → two agents, not one:
- `lane-evaluation-agent` (`agents/catalog.yaml:13-28`):
  `lane.evaluate`, `lane.option.create`, `capacity.check`,
  `carrier-rate.read` — "create optimized shipment routes" +
  "identify lowest freight cost" (read-only rate check, a thin slice
  that also touches the Carrier Procurement Specialist role below — the
  agent boundary doesn't perfectly align to one human job, which is
  realistic: agents are bounded by *action*, humans are bounded by
  *role*).
- `route-decision-agent` (`agents/catalog.yaml:48-63`): `route.
  recommend`, `route-deviation.propose`, `quote.submit-for-approval`,
  `approval.request` — "plan and route shipments" (recommend), with
  the actual approval/submission decision still gated by the Pricing
  Manager above.

Neither agent may `route-deviation.approve` — same human-approves
pattern as the Pricing Manager section above.

Sources: [Velvet Jobs Transportation Planner](https://www.velvetjobs.com/job-descriptions/transportation-planner), [JobDescription.org Load Planner](https://jobdescription.org/jobs/transportation/load-planner)

---

## Platform Administrator — **Modeled** (`aiden.ashford`)

Not a logistics-domain role — IT/platform administration (owns QMS's
`/admin/reset`). Outside the offer-to-cash spine entirely; kept as-is,
no real-world logistics job-title research applies.

---

## Carrier Procurement Specialist — **Modeled, human only** (`human.felix.procurement`)

Department `carrier-procurement` — deliberately distinct from Pricing:
Commercial Pricing *consumes* buy rates, Carrier Procurement *negotiates*
them. No Cedar group, no `member_of`, no `approval_limit`: this
department's `apis`/`mcp`/`agents` maturity in `business/
departments.yaml` is all `future` — added to the org chart one step
ahead of the implementation that would eventually automate part of it
(explicit decision this session: the organization is business-complete
even where the implementation hasn't caught up).

Real responsibilities (from "Carrier Procurement Specialist"/"Carrier
Representative" postings):
- Cultivate carrier relationships while negotiating and securing carriers to move freight
- Negotiate linehaul and accessorial rates
- Maintain continuous communication with carriers and customers
- Inform parties of route modifications, delays, or complications
- Schedule/coordinate pickup and delivery appointments
- Research databases to identify prospective carriers
- Track back-end billing/invoicing to verify carrier charge accuracy

**Agent-delegable subset:** none yet. `lane-evaluation-agent`'s
`carrier-rate.read` touches a thin, read-only slice of this territory
(reading a rate, not negotiating one) — not a delegation of this role,
just an adjacent action owned by the Transport Planner's agent.

Sources: [RXO Carrier Procurement Specialist](https://simplify.jobs/p/f2609f31-2e54-468c-a0cf-7fd0286f046f/Carrier-Procurement-Specialist), [Skypace Ocean Freight Carrier Representative](https://skypace.com/careers/carrier-representative-procurement-specialist-ocean-freight-woodlands-onsite)

---

## Org-complete, not yet implemented

Real, recognizable roles named in `business/departments.yaml` +
`business/job-titles.yaml` with no human in `identity/actors.yaml` yet
— the organization stays visible even where nothing automates or even
runs it today:

- **Account Manager / Sales Manager** (Commercial — CRM, RFQ intake) —
  owns the customer relationship and the RFQ that starts this
  subprocess; RFQ intake itself is upstream of what's modeled here.
- **Operations Planner** (Planning) — placeholder, not yet
  responsibility-researched to the same depth as Transport Planner.
- **Carrier Procurement Manager** (Carrier Procurement) — placeholder.
- **Operations Coordinator / Booking Coordinator** (Operations) —
  downstream of a decision this subprocess makes, not part of making it.
- **Customs & Trade Compliance Specialist** — no compliance/customs
  system exists in this showcase yet.
- **Billing / AR Specialist** (Finance) — downstream of the whole
  subprocess; no ERP/billing system exists in this showcase yet.

If any of these get a human/agent later, ground them the same way: real
job title and real responsibility bullets first (deepen `business/
job-titles.yaml`'s placeholder entry), then derive the directory
identity and (if warranted) an agent as a bounded subset — not the
reverse. Per this session's explicit instruction: deepen the 5 titles
already researched to full depth (responsibilities, systems touched,
produces/consumes, business decisions, KPIs, approval authority,
reports-to/manages) before researching more titles, and before adding
any more identities.
