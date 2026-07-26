# Skill: implement and check an A2A Agent Card in this project

How to build a spec-compliant `AgentCard` for an A2A server in this
monorepo (`a2a-sdk` 1.1.2), and how to verify it against real clients
(A2A Inspector) instead of assuming it's correct because the server boots.

## Background: the bug this skill exists to prevent

All 3 agents (`lane-evaluation-agent`, `route-decision-agent`,
`commercial-normalization-agent`) originally built their `AgentCard` like
this:

```python
supported_interfaces=[
    AgentInterface(
        protocol_binding="JSONRPC",
        protocol_version="1.0",
        url=f"{public_url}/a2a/jsonrpc",
    ),
],
```

This served a **200 OK** from `/.well-known/agent-card.json`, and every
one of this repo's own tests passed (`TestClient` calls, subprocess
network-checkpoint tests). It still broke every *external* A2A client —
A2A Inspector included — with:

```
Failed to validate agent card structure: [{"type":"missing","loc":["url"], ...}]
```

The served JSON had **no top-level `url` field** — only the nested one
inside `supportedInterfaces`. Every internal test was checking `200 OK` +
the fields *we* read (`skills`, `supportedInterfaces`), never validating
against the actual A2A JSON schema an external client expects. That's the
gap this skill closes.

## Root cause (verified against the installed a2a-sdk source, not assumed)

`a2a-sdk` 1.1.2's `AgentCard` is a protobuf-backed type with no top-level
`url` field at all — the modern (protocol version `1.0`) schema expects
clients to read `supportedInterfaces` instead. For **backward
compatibility** with clients still expecting the classic (`0.3`-era) A2A
schema, the SDK's own serializer
(`a2a.server.request_handlers.response_helpers.agent_card_to_dict()`)
tries to synthesize a top-level `url` by calling `to_compat_agent_card()`.

That function only backfills `url` from interfaces whose `protocol_version`
is **empty** or is a **legacy** (`>=0.3, <1.0`) string
(`a2a.compat.v0_3.versions.is_legacy_version()`). An interface explicitly
declaring `protocol_version="1.0"` — the *current* version — is
deliberately excluded from that compat path (the SDK assumes a 1.0-native
client doesn't need the legacy field). A2A Inspector's bundled validator
still requires the legacy `url`, so an interface declaring `"1.0"`
explicitly produces a card that satisfies our own server's tests but fails
every spec-compliant/legacy-aware external client.

**The fix**: don't set `protocol_version` on `AgentInterface` at all.
Leaving it unset (empty string) makes the interface compat-eligible, so
`to_compat_agent_card()` backfills `url` correctly — the served card then
satisfies both old and new clients:

```python
AgentInterface(
    protocol_binding="JSONRPC",
    # protocol_version deliberately left unset -- see this skill for why
    # an explicit "1.0" excludes the interface from the SDK's own
    # backward-compat url-injection path.
    url=f"{public_url}/a2a/jsonrpc",
),
```

## How to implement a new agent's AgentCard correctly

1. Build `supported_interfaces` with `protocol_binding` and `url` set,
   **`protocol_version` left unset** (per the root cause above), unless
   you have a specific reason to pin a legacy version string.
2. Set `url` on the interface to `f"{public_url}/a2a/jsonrpc"` where
   `public_url` comes from `ServiceSettings.from_env(default_port=port).public_url`
   (see `rfq_common.settings`) — never a hardcoded `http://{host}:{port}`
   (that's the separate Caddy-first/public-URL fix from earlier this
   session — both bugs live in the same `_agent_card()` function, don't
   reintroduce the old one while fixing this).
3. Don't hand-roll JSON serialization — use `create_agent_card_routes()`
   from `a2a.server.routes`, which calls the SDK's own
   `agent_card_to_dict()` (the compat-injection logic above lives there;
   duplicating it yourself would drift from the SDK's own behavior on the
   next upgrade).

## How to check it — don't trust your own tests alone

Your own service's tests (TestClient/subprocess-based) will happily pass
even with the bug above, because they only assert `response.status_code == 200`
and check the fields *they* care about. None of that proves the JSON is
valid per the schema an external client enforces. Check it for real:

1. **Fetch the raw JSON and inspect it directly** — the fastest check,
   no external tool needed:
   ```python
   from fastapi.testclient import TestClient
   from lane_evaluation_agent.api import build_app
   c = TestClient(build_app(port=8204))
   d = c.get("/.well-known/agent-card.json").json()
   assert "url" in d, d  # the field that actually broke
   ```
2. **Point A2A Inspector at the running service** (vendored at
   `vendor/a2aproject/a2a-inspector`, containerized via
   `infra/a2a-inspector/docker-compose.yml`, running on port 8092 by
   default). Enter the agent's `/.well-known/agent-card.json` URL (or just
   the base URL) in the inspector UI and confirm it validates without
   error — this is the actual external-client contract check, not a proxy
   for it.
3. If the inspector reports a validation error, read the `loc` field in
   the error precisely (e.g. `["url"]`) and check the *served JSON*
   directly (step 1) before guessing at the server code — the bug is
   almost always in what's missing/shaped wrong in the response, not in
   the inspector.

## Don't assume backward-compat interface shapes without checking the SDK version

The behavior described here (`protocol_version="1.0"` opting OUT of
compat) is specific to `a2a-sdk` 1.1.2's `to_compat_agent_card()`
implementation. If this repo upgrades `a2a-sdk`, re-check
`a2a.server.request_handlers.response_helpers.agent_card_to_dict()` and
`a2a.compat.v0_3.versions.is_legacy_version()` directly (read the
installed package source, don't assume the same rule still holds) before
assuming the unset-`protocol_version` fix is still correct.
