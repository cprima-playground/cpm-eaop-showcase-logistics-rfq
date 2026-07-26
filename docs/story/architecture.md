# The agent architecture in plain language

## Four layers

| Layer | Plain-language question | Showcase concept |
| --- | --- | --- |
| Business | What needs to happen? | Reprice a quote when currency or route conditions change |
| Collaboration | Which specialist does the next piece of work? | A2A delegation between agents |
| Access | How does a specialist use enterprise capabilities? | MCP tools over existing system APIs |
| Governance | Is this identity allowed to cause this business effect? | AuthN, PEP, PDP, policy, and obligations |

## One business event, many coordinated capabilities

The flagship story begins when the business world changes: an exchange rate
moves, a route becomes unavailable, or both happen together.

1. The event identifies quotes that may be affected.
2. An agent obtains the relevant operational and commercial facts.
3. Agents compare route options and normalize costs.
4. Policy evaluates thresholds such as margin, FX variance, route cost, transit
   time, and delegated approval limits.
5. A human reviews and approves where the policy requires judgment.
6. The authoritative quote and operational systems are updated.

The agents orchestrate the work. The systems of record retain the facts and
durable business state.

## What A2A and MCP are not

- A2A is not a replacement for a system of record. It carries collaboration
  between agents.
- MCP is not a replacement for a TMS or QMS API. It exposes selected business
  capabilities to agents in a controlled way.
- An agent is not a new master-data store. It should not silently become the
  authority for customers, routes, rates, or approvals.
