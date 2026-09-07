# Spike: hello-agent-adk

**Decision being verified:** can this repo deploy and invoke a Vertex AI
Agent Engine (ADK) agent for real, from `cpm-geap-2026` — the project this
repo already has GCP API inventory for, distinct from the not-yet-created
`rfq-showcase-test`/`prod` this repo's own `data/env/environments.yaml`
declares as its eventual target.

**Hypothesis:** the deploy mechanics already proven in `cpm-eaop`
(`src/spike/geap/geap/agents/hello_agent/`) — `vertexai.agent_engines.create()`
against `cpm-geap-2026` — port directly into this repo with no
project-specific integration surface (no control-panel/Keycloak/UiPath
coupling, unlike the `cpm-eaop` original).

**Interfaces implemented:** `agent.py` (bare ADK `Agent`, no tools),
`deploy.py` (`agent_engines.create`, not `.update` — this is a new resource,
distinct from `cpm-eaop`'s `3161528587681529856`), `trigger.py`
(`stream_query` smoke test against a resource name passed as an argument).

**Deliberate simplifications:** no tools, no control-panel wiring, no
Terraform, no Keycloak/Entra identity — proves deploy+invoke round-trip
only, not this repo's actual agent architecture (its 3 real agents are
plain `a2a-sdk` FastAPI services, not ADK, and stay that way — see
`decisions/ADR-008-agent-runtime.md` for why ADK/Agent Engine is target-state
only today).

**Test scenarios:** `uv run deploy.py` creates the resource;
`uv run trigger.py <resource_name>` sends one query and expects a reply
prefixed `[ADK/Vertex AI - showcase]`.

**Evidence:** resource id recorded in
`data/agents/hello-agent-adk-gcp.yaml` after deploy.

**Result:** decision supported. Deployed 2026-07-31 to
`projects/200607526455/locations/us-central1/reasoningEngines/504070555998093312`
(`cpm-geap-2026`); `trigger.py` round-trip returned
`[ADK/Vertex AI - showcase] Four.` — deploy+invoke mechanics work from this
repo with no dependency on `cpm-eaop`'s control-panel/Keycloak wiring.

**Architecture consequence:** if this works, it's concrete evidence for
`agent-execution-runtime`/`geap-agent-runtime` in an external
building-blocks catalog — Vertex AI Agent Engine was previously only
*declared* (ADR-008), never demonstrated from this repo.

**Open questions:** whether `rfq-showcase-test`/`prod` (this repo's own
declared target) vs. `cpm-geap-2026` (what this spike actually used) ever
gets reconciled — explicitly out of scope here.
