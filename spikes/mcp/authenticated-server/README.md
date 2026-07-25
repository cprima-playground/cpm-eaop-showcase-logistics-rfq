# Authenticated MCP server spike

One standalone Python MCP server for exploring authenticated Streamable HTTP
with the local Keycloak instance. This first spike deliberately has no Cedar
policy engine and no agent implementation.

## Endpoint

The default host mapping is:

```text
http://localhost:8091/mcp
```

The container listens on port `8000`; `8091` avoids the repository's existing
local ports. The server also exposes `/healthz` through the FastMCP/ASGI app
only if the SDK version provides it; the MCP endpoint is the contract under
test.

## Start

Start the local Keycloak from the repository root if it is not already running:

```powershell
docker compose -f infra/keycloak/docker-compose.yml up -d
```

Create/apply the local realm and clients using the existing instructions in
`infra/keycloak/README.md`. Then start the spike:

```powershell
cd spikes/mcp/authenticated-server
uv lock
docker compose up --build
```

Connect MCP Inspector to:

```text
http://localhost:8091/mcp
```

The MCP server validates bearer tokens through Keycloak's RFC 7662 token
introspection endpoint. The helper uses `host.docker.internal` when obtaining
the token so its issuer matches the hostname used inside the MCP container.
Configure a confidential introspection client when
Keycloak requires client authentication:

```powershell
$env:MCP_INTROSPECTION_CLIENT_ID = "mcp-auth-spike"
$env:MCP_INTROSPECTION_CLIENT_SECRET = "..."
docker compose up --build
```

The token must be active. An optional audience and scope can be enforced with:

```powershell
$env:MCP_EXPECTED_AUDIENCE = "mcp-auth-spike"
$env:MCP_REQUIRED_SCOPE = "mcp:invoke"
```

Leave both unset for the initial authentication-only experiment.

## Available capabilities

- `echo_authenticated`: protected tool returning non-secret caller metadata.
- `demo://authenticated-contract`: protected resource describing the header contract.

The tool/resource responses are diagnostic only. They do not implement business
authorization.

## Contract under test

Protocol headers are handled by MCP:

- `Accept: application/json, text/event-stream`
- `Content-Type: application/json`
- `MCP-Protocol-Version` after initialization
- `MCP-Session-Id` when returned by the server

The platform headers are:

- `Authorization: Bearer ...`
- `X-Correlation-Id`
- `traceparent`

The server echoes or generates `X-Correlation-Id` on HTTP responses. Access
tokens are never logged or returned.

## Current limitation

This is an authentication and transport spike. It uses token introspection and
does not yet perform Cedar evaluation, tool-level domain-action mapping, or
delegated token exchange. Those will be added at the policy gateway stage.
