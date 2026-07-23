# Token fixtures

One claim fixture per principal in the scenarios, honoring the claim contract
(`../../identity/claims-contract.md`). Mirrors cpm-eaop `tests/spike/fixtures/entra/`
(`<name>.claims.json`), frozen `iat` 2026-01-01 / `exp` 2099, patterned GUIDs.

To add (per principal):
- `lane-evaluation-agent.claims.json`        (azp in registry → kind=agent)
- `commercial-normalization-agent.claims.json`
- `route-decision-agent.claims.json`
- `mona.commercial.claims.json`              (human: tid/oid/groups; role: route-deviation.approve; group rfq-commercial-emea)

Each resolves via `resolve_principal` to the InternalPrincipal the PDP evaluates.
Agents authenticate as services with a `keycloak_client` from `agents/catalog.yaml`.
