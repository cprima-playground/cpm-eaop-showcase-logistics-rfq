# ADR-003 — Agent + tool boundaries

**Status:** accepted.
**Context:** the repricing subprocess needs agents with clear responsibilities and a
defensible role for each integration technology (not "MCP for everything").

## Decision

**Three agents**, each owning execution of specific domain actions (`agents/catalog.yaml`):

- **Lane Evaluation** — build/compare routes (does not convert currency or approve).
- **Commercial Normalization** — FX + cost normalization + margin (does not approve).
- **Route Decision** — **recommends**, never approves; opens the human task.

**Technology per role** (each defensible):

| Purpose | Tech |
| --- | --- |
| agent → internal system of record | **MCP** |
| agent → external FX rate | **direct HTTP API** |
| agent → agent task/result | **A2A** |

**Every governed edge is authorized:** `agent.delegate` (A2A, depth ≤ 1),
`mcp.connect`/`tool.call`, bound to **domain actions** (`carrier-rate.read`), never a
generic `mcp.call`. Tools map to domain actions via `x-domain-action`.

## Rationale

- Separation of duties (recommend vs approve) is the governance story.
- One technology per integration seam keeps each choice justifiable.
- Domain-action binding gives Cedar meaningful subjects, not transport verbs.

## Alternatives

- **One mega-agent** — rejected: no separation of duties, nothing to govern between.
- **MCP for FX** — rejected: FX is a narrow deterministic API, not an SoR.

## Consequences

- A2A chain lane → commercial → route (`interfaces/a2a/handoff.md`), delegation depth 1.
- Agents run on the ADK (ADR-008); each is a container in dev.
- The second boundary (tool→API) is out of scope (ADR-008 Related).
