# Governance policies — repricing subprocess

Two visibly separate policy categories (per the seed + cpm-eaop split):

- **Business authorization** (`policies.cedar`) — *may this principal perform this
  domain action on this resource in this context?* (D1–D7).
- **Governance** (this file) — governs the agent **platform itself**, independent of
  the RFQ domain.

## Governance actions (mirror cpm-eaop `data/policies/actions.yaml`)

```text
platform.eligible · agent.invoke · agent.delegate · agent.disable · agent.enable
· tool.call · mcp.connect · grant.issue
```

For the repricing slice, the governed edges are:
- `agent.delegate` — Lane → Commercial → Route Decision (A2A), bounded to depth 1
  (obligation `oblig-delegation-depth-1`).
- `mcp.connect` / `tool.call` — each agent → its MCP servers (`interfaces/mcp/`).
- `agent.disable` — the kill switch (below).

## Kill switch — scopes, not a boolean

Model several scopes, not one flag (checked before an A2A task is accepted, an MCP
tool runs, a grant is issued, or a side effect commits):

```yaml
kill_switches:
  - {id: global-repricing, scope: platform, status: enabled}
  - {id: commercial-agent, scope: agent, target: commercial-normalization-agent, status: enabled}
  - {id: fx-tool,          scope: tool,  target: get_exchange_rate, status: enabled}
  - {id: customer-acme,    scope: customer, target: ACME, status: enabled}
```

### Fail behavior when the kill-switch lookup is unavailable

| Component | Behavior |
| --- | --- |
| read-only lane/rate lookup | fail closed or cached decision |
| FX read / cost normalization | fail closed |
| quote submit / route recommend | fail closed |
| human-approval write-back | fail closed |

## Governance decision (example)

```text
Principal: OperationsAdmin   Action: agent.disable
Resource:  CommercialNormalizationAgent
Context:   incident_ref present · environment = showcase · principal has emergency-operator role
```

Enforcement of governance obligations (delegation depth, kill-switch state) is a
PEP concern (`enforce.py`-style), same as the business obligations.
