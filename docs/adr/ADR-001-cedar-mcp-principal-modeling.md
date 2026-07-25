# ADR-001: Cedar MCP-principal modeling

Status: Accepted
Date: 2026-07-25

## Context

The showcase needs MCP servers to be first-class Cedar principals
(`Workload`), distinct from the existing `Principal` (human) and
`AgentPrincipal` (autonomous agent) entity types, so that agent-to-MCP
transport and MCP-mediated tool calls are Cedar-authorized rather than
merely OAuth-authenticated. Three concrete modeling questions block
milestone M1 (`authorization/authz-projection.yaml` +
`business/actions.yaml` changes):

1. Does an MCP server's identity need a new Cedar entity type, and what
   shape (attributes, parents)?
2. Do MCP tools (`interfaces/mcp/tools.yaml`) need their own Cedar
   entity type (`MCPTool`/`AgentTool`), or can they be represented some
   other way?
3. What does the transport-level "may this agent open a session with
   this MCP server" action look like, and — per the implementation
   plan's decision #3 — how does an MCP-mediated tool call carry both
   the initiating caller's identity and the executing workload's
   identity through to Cedar?

This ADR resolves only these three questions. It does not decide
seed-data content (M2), the identity-provisioning pipeline (M3.x), or
delegation semantics (ADR-003, explicitly deferred).

## Decision

### 1. `Workload` entity type

New entity type, sibling to `Principal`/`AgentPrincipal` (not a subtype
of either):

```yaml
Workload:
  ontology: null
  parents: []                # no group membership by default
  attributes:
    kind: String              # "workload"
    active: Boolean
    system: String            # which business system it wraps, e.g. "tms"
    trust_domain: {type: String, required: false}
```

No `parents: [Group]` — workloads don't get business-role group
membership by default (per the roadmap's taxonomy decision: Cedar
policy decides a workload's permitted actions, not group membership).
If a concrete future policy needs a workload in a group, add `parents`
then, as a deliberate, reviewed change — not preemptively.

### 2. MCP tools: context attribute, not a new entity type

`MCPTool`/`AgentTool` are **not** introduced as Cedar entity types.
Reasoning: `interfaces/mcp/tools.yaml` already maps each tool 1:1 to an
existing Cedar action (e.g. `tms-mcp.check_lane_capacity` →
`capacity.check`). A separate `MCPTool` entity would duplicate that
mapping as data without adding expressiveness, since no policy in
`authorization/policies.cedar` today needs to reference a *specific
tool* as a resource independent of the action it maps to (e.g. "deny
tool X regardless of which action it triggers" — not a scenario that
exists).

Instead, the tool name travels as a **context attribute** on the
action itself, alongside the executing workload (question 3). Revisit
this decision — introduce a real `MCPTool` entity — only if a concrete
future policy needs to reference a tool as a resource distinct from its
mapped action.

### 3. Transport action + context propagation shape

New action, `mcp.connect` — the transport-level "may this agent even
open a session with this workload" check, independent of any specific
tool call within that session:

```yaml
mcp.connect:
  principals: [AgentPrincipal]
  resources: [Workload]
```

No context needed — this checks agent-to-workload eligibility (e.g. by
`trust_domain`), which is expressible via entity attribute comparison
in the policy, not per-request context.

**Per-tool-call context propagation** (implementation plan decision
#3): every existing action reachable via an MCP tool call gets two
additional **optional** context attributes, added to
`business/actions.yaml`'s per-action `context:` block:

```yaml
context:
  executing_workload: {type: String, required: false}
  tool: {type: String, required: false}
```

Optional, not required: actions also reachable via a non-MCP path
(e.g. a human using the QMS UI directly) legitimately have no
`executing_workload`/`tool` context. Policies that care about the
MCP-mediated case check for the attribute's presence; policies that
don't care ignore it. This keeps the Cedar request shape uniform:

```text
principal = initiating caller (Agent::"agent.lane-evaluation")
action    = the tool's mapped action (per tools.yaml)
resource  = the business resource (per business/actions.yaml)
context.executing_workload = Workload::"workload.tms-mcp"
context.tool = "check_lane_capacity"
```

The **principal is always the initiating caller**, never the MCP
server itself — the workload's own credential authenticates its
service-to-service call to the wrapped business system (transport
auth), it is not what Cedar evaluates the tool-call permission against.

## Consequences

- M1 adds exactly one entity type (`Workload`) and one action
  (`mcp.connect`) to the schema, plus two optional context fields to
  every action `interfaces/mcp/tools.yaml` currently maps a tool to:
  `lane.evaluate`, `capacity.check`, `carrier-rate.read`,
  `quote-price.calculate`, `quote-variance.evaluate`,
  `route-cost.normalize`, `approval.request`, `route-deviation.propose`,
  `route.recommend` (9 actions — verified against `tools.yaml`'s actual
  tool list, not assumed). `lane.option.create` and
  `quote.submit-for-approval` are not currently mapped by any MCP tool
  and are unchanged.
- No `MCPTool` entity now; revisiting this later is additive (a new
  entity type + updated actions), not a breaking change to what M1
  ships.
- `agents/catalog.yaml`'s `can_call` graph (agent-to-agent, not
  agent-to-workload) is explicitly out of this ADR's scope — it's an
  entity-*instance*/relationship question, deferred to M3.5 per the
  implementation plan's decision #10, not a schema question this ADR
  needs to resolve.
