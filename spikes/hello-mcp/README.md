# Spike: hello-mcp

**Decision being verified:** can this repo build and deploy a genuine
MCP-protocol server (not this repo's `tms-mcp`-style FastAPI-REST-labeled
pattern) to Cloud Run in `cpm-geap-2026`, and have it respond correctly to a
real MCP client over HTTPS.

**Hypothesis:** the `mcp` SDK's `MCPServer` (streamable-http transport)
can be containerized with a plain Dockerfile and deployed via
`gcloud run deploy --source`, same spirit as `spikes/hello-agent-adk`'s
Vertex AI Agent Engine deploy.

**Interfaces implemented:** `hello_mcp/server.py` (one tool, `say_hello`,
no identity/policy wiring), `Dockerfile` (no BuildKit `--mount` - Cloud
Build's default docker builder doesn't support it, unlike `src/*/Dockerfile`
services built via `docker compose`).

**Deliberate simplifications:** `--allow-unauthenticated`, no tools beyond
one trivial greeting, no Cedar PDP/PEP, no OIDC - proves deploy+invoke
mechanics only, not this repo's actual MCP security posture (see `tms-mcp`
for that).

**Test scenarios:** local (`uv run hello-mcp` + a real
`mcp.client.streamable_http` session, not just calling the Python function
directly) and remote (same client, against the live Cloud Run URL).

**Evidence:** `data/mcp-servers/hello-mcp-gcp.yaml`.

**Result:** decision supported. Deployed 2026-07-31 to
`https://hello-mcp-200607526455.us-central1.run.app` (Cloud Run,
`cpm-geap-2026`). A real MCP client's `list_tools()` returned `['say_hello']`
and `call_tool('say_hello', {'name': 'cloud-run'})` returned
`[hello-mcp] Hello, cloud-run!` - both locally and against the deployed
Cloud Run URL.

**Architecture consequence:** concrete evidence for `data-connector-mcp` /
`custom-mcp-connector` in an external building-blocks catalog - a genuine
MCP-protocol server (not FastAPI-REST) deployed to Cloud Run, distinct from
(and complementary to) the `qms-mcp`/`rate-mcp`/`tms-mcp`/`approval-mcp`
evidence already cited there.

**Open questions:** the installed `mcp` SDK renamed `FastMCP` to
`MCPServer` and changed `streamable_http_client`'s return arity (2-tuple,
not 3) since older examples/docs - worth checking this again before reusing
this pattern, in case the SDK moves again.
