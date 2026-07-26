# A logistics business becomes agentic — without replacing its enterprise

## 1. Start with the logistics company

A logistics company does not run its business in one generic application. It
uses a landscape of specialized systems, often commercial products, in-house
applications, or a mixture of both.

The names vary by company, but the responsibilities are familiar:

| Business need | Typical system | What it knows authoritatively |
| --- | --- | --- |
| Customer relationship and incoming requests | CRM / RFQ intake | Customers, opportunities, and requests for quotation |
| Transport planning and execution | TMS | Routes, legs, capacity, shipment status, and operational plans |
| Prices and carrier buy rates | Rate management / procurement system | Carrier rates, surcharges, contracts, and validity |
| Commercial quotation | QMS / quotation system | Quote versions, prices, margins, validity, and approval state |
| Reference facts | Master-data service | Parties, locations, currencies, commodities, equipment, and terms |
| Exchange rates | FX service | Currency rates and conversion history |
| Approval and workflow | Workflow / task system | Tasks, notifications, escalations, and human responses |

These systems are not accidental technical clutter. They reflect different
business owners, different update frequencies, and different definitions of
what must be trusted. A route being available is an operational fact. A quoted
price being approved is a commercial fact. The systems of record remain the
authorities for those facts.

## 2. Start from recognizable jobs

The same landscape is visible in job descriptions. A Transport Planner may plan
routes and check capacity. A Commercial Pricing Specialist may prepare quotes,
compare rates, and analyze currency movements. A Pricing Manager may define
pricing governance and approve exceptions.

The showcase does not say that an agent replaces a job. It asks a narrower,
more useful question:

> Which one to three responsibilities in a real job description are structured
> enough to be performed by an agent, while the surrounding judgment and
> accountability remain with people?

For example:

- From the Transport Planner role: evaluate route alternatives, check capacity,
  and prepare a recommendation.
- From the Commercial Pricing Specialist role: normalize route costs into a
  common currency, calculate quote variance, and prepare a quote for review.
- From the Pricing Manager role: retain approval authority for commercial
  deviations and exceptions.

This is the bridge from organizational reality to agent design. The role exists
before the agent. The agent is a bounded capability derived from selected
responsibilities in that role.

See the [role catalog](roles.md) for the current repository-derived view.

## 3. Agents are specialized workers

The showcase models three collaborating workers:

- The **Lane Evaluation Agent** builds and compares feasible route options.
- The **Commercial Normalization Agent** makes costs comparable, calculates
  commercial impact, and prepares a quote for approval when appropriate.
- The **Route Decision Agent** recommends a route and escalates threshold
  crossings to a human.

Each agent has a limited business vocabulary, explicit capabilities, and
explicit prohibitions. In particular, agents do not own the RFQ or the Quote,
and the approval decision remains human.

## 4. Agents collaborate through A2A

The agents do not need to know each other's internal code. They exchange a
business task and its result through **A2A** (Agent2Agent):

```text
Lane Evaluation Agent
        └── route/capacity task ──► Commercial Normalization Agent
                                      └── decision task ──► Route Decision Agent
```

A2A is therefore the collaboration language between specialized workers. It
supports delegation without turning every agent into a dependency on every
other agent's implementation.

## 5. Agents access systems through MCP, above existing APIs

Agents still need facts and actions from enterprise systems. **MCP** provides a
controlled tool interface for that access. It does not replace the TMS, QMS, or
rate system, and it does not replace their APIs.

```text
Agent
  ↓ business tool, exposed through MCP
MCP server
  ↓ existing system API
TMS / QMS / Rate / Approval system
```

This separation is useful. The agent sees a capability such as “check lane
capacity” or “calculate quote variance”. The underlying MCP server translates
that capability into the appropriate API call while applying the enterprise
controls for the call.

## 6. Systems of record continue through the agent era

The most important enterprise message is continuity:

> Agentification changes how people and software interact with enterprise
> systems. It does not make agents the owners of enterprise truth.

The TMS remains authoritative for transport facts. The quotation system remains
authoritative for quote facts. The rate system remains authoritative for rates.
Agents carry working context and recommendations, then read from or write back
to the appropriate system of record through governed capabilities.

This principle applies to systems that existed in the past, systems in use now,
and systems a company introduces in the future. An agent layer can adapt the
interaction model while preserving ownership and auditability.

## 7. The provocative analogy: a fuzzy enterprise service bus

Traditional enterprise service buses route deterministic messages between
known systems. Agents can be seen as a **fuzzy enterprise service bus**: they
interpret a business situation, decide which specialized capability is needed,
and coordinate a path across systems and workers.

The analogy is deliberately provocative. Agents add interpretation and
adaptation; they do not eliminate the need for explicit interfaces, contracts,
identity, authorization, or audit. The fuzzier the orchestration becomes, the
more important those controls become.

## 8. Governed autonomy

Once agents can communicate and invoke enterprise capabilities, two questions
must be answered at every meaningful boundary:

1. **Authentication (AuthN):** Who or what is making this request?
2. **Authorization (AuthZ):** May that identity perform this business action on
   this resource in this context?

The showcase places a Policy Enforcement Point (PEP) in the control path. The
PEP sends the decision question to a Policy Decision Point (PDP), enforces the
answer, and applies any obligations such as human approval or notification.

```text
Agent ──► control-panel PEP ──► policy/PDP ──► allow, deny, or obligation
   │              │
   │              └──────────────► governed MCP/API action
   └───────────── A2A delegation is governed too
```

A2A and MCP provide connectivity. AuthN establishes identity. The PEP/PDP
decides whether the connection may produce a business effect. That is what
turns autonomous activity into governed autonomous enterprise.
