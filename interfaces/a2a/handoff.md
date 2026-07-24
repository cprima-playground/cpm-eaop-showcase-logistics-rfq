# A2A handoff — repricing subprocess

A2A carries **task delegation + result handoff** between the three agents. Reuses
the a2a-sdk 1.1 agent-card shape (mirror cpm-eaop `src/spike/a2a/hello_a2a/agent-card.json`).
Each edge is a governed `agent.delegate` (governance-policies.md), bounded to depth 1.

```text
Lane Evaluation Agent
    └─ A2A ─► Commercial Normalization Agent
                  └─ A2A ─► Route Decision Agent
```

Technology roles kept distinct (each defensible, not "MCP for everything"):

| Purpose | Technology |
| --- | --- |
| agent → internal system of record | MCP (`interfaces/mcp/tools.yaml`) |
| agent → external FX rate | direct HTTP API (`src/mock-fx/`, live `/openapi.json`) |
| agent → agent task/result | A2A (this file) |

## Agent card (shape sketch — TARGET)

```json
{
  "name": "commercial-normalization-agent",
  "description": "Normalizes route costs into the quote currency using authoritative FX.",
  "url": "TARGET",
  "version": "0.1.0",
  "capabilities": { "streaming": false },
  "skills": [
    { "id": "route-cost.normalize", "name": "Normalize route cost",
      "inputModes": ["application/json"], "outputModes": ["application/json"] }
  ],
  "securityScheme": "oauth2-client-credentials",
  "expectedClaims": ["azp", "scope"]
}
```

Each card carries: name · identity/client id · capabilities · supported message
types · endpoint · auth scheme · expected claims · delegation support · I/O schemas.
The delegation edge and its depth limit are authorization concerns, not card fields.
