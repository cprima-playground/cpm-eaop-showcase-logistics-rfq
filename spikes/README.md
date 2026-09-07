# Spikes

Each spike verifies a specific architecture decision and **ends in a verdict** —
*decision supported* / *decision rejected* / *more evidence required*. A spike is
never an undocumented prototype.

Spike template (per `spikes/<name>/README.md`): Decision being verified · Hypothesis
· Interfaces implemented · Deliberate simplifications · Test scenarios · Evidence ·
Result · Architecture consequence · Open questions.

| Spike | Verifies | Status |
| --- | --- | --- |
| [`repricing/`](repricing/README.md) | Cross-Currency Lane Repricing and Approval — event-driven agentic slice with FX normalization, distinct threshold policies, deny-precedence, and human-in-the-loop | **defined (no code yet)** |
| [`hello-agent-adk/`](hello-agent-adk/README.md) | Vertex AI Agent Engine (ADK) deploy+invoke mechanics work from this repo, against `cpm-geap-2026` | **decision supported** |
| [`hello-mcp/`](hello-mcp/README.md) | Real MCP-protocol server (not FastAPI-REST-labeled like `tms-mcp`) deploy+invoke mechanics work via Cloud Run, against `cpm-geap-2026` | **decision supported** |

> This pass **documents** the spike. No code is implemented. The mock services and
> agents below are specified, not built.
