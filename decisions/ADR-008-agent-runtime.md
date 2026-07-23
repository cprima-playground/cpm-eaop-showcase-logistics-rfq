# ADR-008 — Agent runtime

**Status:** accepted.
**Context:** the three repricing agents (`../agents/catalog.yaml`) need a runtime. The
showcase is about **agent governance on an agent platform** — so use the real agent
platform, not a generic container, where it matters.

## Decision

**Agents run on Vertex AI Agent Engine (ADK) on GCP** (test + demo/prod). In **dev**
they run as **local containers** (same agent code, plain container host) so
development stays local + free — env-conditional, like identity.

| Env | Agent host |
| --- | --- |
| dev | local container (`docker compose`) — free |
| test | **Vertex AI Agent Engine** (personal GCP) |
| demo/prod | **Vertex AI Agent Engine** (corporate GCP) |

Rationale:
- The showcase's point is governing agents; hosting them on the actual **agent
  platform** (Vertex Agent Engine + ADK) makes the story real, not simulated.
- **Matches cpm-eaop** `hello-agent-gcp` (Vertex AI Agent Engine + ADK, WIF identity).
- Fits the identity decision (ADR-006 §4): a Vertex agent's GCP SA federates to Entra
  via **WIF** — no stored secret.
- A2A between agents (`../interfaces/a2a/handoff.md`) is hosted consistently.

## Alternatives

- **Cloud Run for agents** — portable, cheaper, but weaker "agent platform" narrative;
  the mock *systems* already run on Cloud Run, so keep agents on the platform meant
  for agents. Used only as the **dev** stand-in.

## How dev-local is achieved (ADK is the portability layer)

Agents are written to the **ADK** — host-agnostic. Same code, two hosts:

- **Dev (local, free):** run the ADK agent **in a container** (compose) — one image
  per agent, consistent with the one-image-per-component strategy (`../deploy/containers.md`).
  The ADK runner runs *inside* the container; A2A between agent containers over the
  compose/Caddy network. (Not bare-host `adk run` — containerized, so dev == the
  shape that deploys.) No GCP, no Vertex.
- **Test/prod:** deploy the *same* agent to Vertex Agent Engine
  (`agent_engines.create()`); host swaps by env, code unchanged.

**Zero-cost + deterministic reasoning:** scenarios are scripted (`given/when/then`),
so agent decisions are deterministic. **Stub/mock the LLM in dev** (canned per-scenario
responses) — no model cost, and it removes the "non-deterministic model output" risk
for the demo. Real Gemini only in test/prod (or a free-tier key). The determinism
contract (`../RUNNING.md`) assumes the stub in dev.

## Consequences

- Agent code is written to the **ADK**; dev runs it in a container, test/prod deploy it
  to Agent Engine — one codebase, env-conditional host (`../deploy/environments.md`).
- `../infra/terraform` provisions Agent Engine + the WIF federated credentials on GCP.
- Dev remains **zero-cost**: no Vertex locally.

## Related — the second authorization boundary is OUT OF SCOPE

The platform architecture has **two correlated boundaries** (agent→tool, then
tool→API). **This showcase governs only the first** (agent→tool, via Cedar). The
tool→API boundary is an **implementation** concern, not modeled here — *this is a
showcase, not the implementation*. Recorded so the "two boundaries" principle in the
target architecture isn't mistaken for a showcase gap.
