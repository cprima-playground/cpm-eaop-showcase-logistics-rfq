# Machine-identity / trust-boundary inventory

GENERATED -- do not hand-edit. Source: `identity/credentials-inventory.yaml` + a small static list of edges that carry no credential at all (see `tools/identity/gen_machine_identity_inventory.py`'s `_STATIC_EDGES`). Re-run `uv run python -m tools.identity.gen_machine_identity_inventory` after any change to `identity/credentials-inventory.yaml`.

Every service-to-service auth edge this repo actually has (decision #8, M6). Any edge with a weaker-than-workload-token mechanism (`shared API key`, `none`) is a DELIBERATE, ALREADY-ACCEPTED scope call, documented at the credential's own `note` in `identity/credentials-inventory.yaml` -- not a silent gap.

| Caller | Target | Mechanism | Status |
| --- | --- | --- | --- |
| approval-mcp | Keycloak (token introspection, RFC 7662) | OIDC confidential client, workload's own identity (approval-mcp-svc-client-secret) | real |
| approval-mcp | mock-qms | shared API key (qms-api-key) | real |
| commercial-normalization-agent | mock-fx | shared API key (fx-api-key) | real |
| commercial-normalization-agent | mock-masterdata | shared API key (masterdata-api-key) | real |
| commercial-normalization-agent | mock-qms | shared API key (qms-api-key) | real |
| geo-api | Keycloak (token introspection, RFC 7662) | OIDC confidential client, workload's own identity (geo-api-svc-client-secret) | real |
| infra/keycloak/terraform (Terraform apply, human-triggered) | Keycloak admin API | keycloak-realm-admin-password (identity/credentials-inventory.yaml) | real |
| lane-evaluation-agent | mock-masterdata | shared API key (masterdata-api-key) | real |
| lane-evaluation-agent | mock-rate | shared API key (rate-api-key) | real |
| lane-evaluation-agent | mock-tms | shared API key (tms-api-key) | real |
| mission-control-api | Keycloak (token introspection, RFC 7662) | OIDC confidential client, workload's own identity (mission-control-api-svc-client-secret) | real |
| mock-fx | mock-masterdata | shared API key (masterdata-api-key) | real |
| mock-rate | mock-masterdata | shared API key (masterdata-api-key) | real |
| mock-tms | mock-masterdata | shared API key (masterdata-api-key) | real |
| ops-dashboard | Keycloak (token introspection, RFC 7662) | OIDC confidential client, workload's own identity (ops-dashboard-svc-client-secret) | real |
| qms-mcp | Keycloak (token introspection, RFC 7662) | OIDC confidential client, workload's own identity (qms-mcp-svc-client-secret) | real |
| qms-mcp | mock-fx | shared API key (fx-api-key) | real |
| qms-mcp | mock-qms | shared API key (qms-api-key) | real |
| rate-mcp | Keycloak (token introspection, RFC 7662) | OIDC confidential client, workload's own identity (rate-mcp-svc-client-secret) | real |
| rate-mcp | mock-rate | shared API key (rate-api-key) | real |
| rfq_common.pdp.PDPClient (every service that authorizes) | cedar-agent | none -- network-only trust | accepted exception |
| route-decision-agent | mock-masterdata | shared API key (masterdata-api-key) | real |
| tms-mcp | Keycloak (token introspection, RFC 7662) | OIDC confidential client, workload's own identity (tms-mcp-svc-client-secret) | real |
| tms-mcp | mock-tms | shared API key (tms-api-key) | real |

## Notes

- **approval-mcp -> Keycloak (token introspection, RFC 7662)**: value comes from the approval-mcp-svc client Keycloak already provisions (infra/keycloak/terraform's machine_identities for_each) -- fetched live via the Keycloak admin API and recorded here, same posture as qms-mcp-svc-client-secret above; seed.py must not overwrite it with a random value.
- **approval-mcp -> mock-qms**: (credential-level note, shared by every consumer of qms-api-key) qms-mcp AND approval-mcp both reuse this shared key as their own
transport credential to mock-qms (M6, same posture tms-mcp/
tms-api-key established) rather than minting a per-MCP-server key
-- decision #8's accepted weaker-than-per-workload-token granularity
for this hop. The two servers sharing mock-qms is only valid under
ADR-002 because their EXPOSED action sets are disjoint (mechanically
checked, see src/qms-mcp/tests/test_adr002_disjointness.py) -- this
shared-key note documents the transport layer, not the authorization
layer, and does not itself relax that requirement.
- **commercial-normalization-agent -> mock-fx**: (credential-level note, shared by every consumer of fx-api-key) qms-mcp's route-cost.normalize tool consults mock-fx directly (real
fx_age_seconds for D2's already-decided freshness gate, then the
real conversion via mock-fx's own /convert) -- reuses the shared
key, same posture as tms-mcp/tms-api-key et al (decision #8).
- **commercial-normalization-agent -> mock-qms**: (credential-level note, shared by every consumer of qms-api-key) qms-mcp AND approval-mcp both reuse this shared key as their own
transport credential to mock-qms (M6, same posture tms-mcp/
tms-api-key established) rather than minting a per-MCP-server key
-- decision #8's accepted weaker-than-per-workload-token granularity
for this hop. The two servers sharing mock-qms is only valid under
ADR-002 because their EXPOSED action sets are disjoint (mechanically
checked, see src/qms-mcp/tests/test_adr002_disjointness.py) -- this
shared-key note documents the transport layer, not the authorization
layer, and does not itself relax that requirement.
- **geo-api -> Keycloak (token introspection, RFC 7662)**: value comes from the geo-api-svc client Keycloak already provisions (infra/keycloak/terraform's machine_identities for_each) -- fetched live via the Keycloak admin API and recorded here, same posture as qms-mcp-svc-client-secret/approval-mcp-svc-client-secret above; seed.py must not overwrite it with a random value.
- **infra/keycloak/terraform (Terraform apply, human-triggered) -> Keycloak admin API**: Provisions realm/clients/workload identities -- not a runtime service edge, an operator edge.
- **lane-evaluation-agent -> mock-rate**: (credential-level note, shared by every consumer of rate-api-key) rate-mcp reuses this shared key as its own transport credential to
mock-rate (M6, same posture tms-mcp/tms-api-key established in M6a)
rather than minting a per-MCP-server key -- decision #8's accepted
weaker-than-per-workload-token granularity for this hop.
- **lane-evaluation-agent -> mock-tms**: (credential-level note, shared by every consumer of tms-api-key) tms-mcp reuses this shared key as its own transport credential to mock-tms
(M6a) rather than minting a per-MCP-server key -- decision #8's accepted
weaker-than-per-workload-token granularity, already the repo's existing
posture for this hop (unchanged behavior for the other two consumers).
A dedicated tms-mcp-api-key entry remains status:planned below for a
future tightening, not activated by this milestone.
- **mission-control-api -> Keycloak (token introspection, RFC 7662)**: value comes from the mission-control-api-svc client Keycloak already provisions (infra/keycloak/terraform's machine_identities for_each) -- fetched live via the Keycloak admin API and recorded here, same posture as tms-mcp-svc-client-secret/rate-mcp-svc-client-secret/ qms-mcp-svc-client-secret/approval-mcp-svc-client-secret above; seed.py must not overwrite it with a random value.
- **ops-dashboard -> Keycloak (token introspection, RFC 7662)**: value comes from the ops-dashboard-svc client Keycloak already provisions (infra/keycloak/terraform's machine_identities for_each) -- fetched live via the Keycloak admin API and recorded here, same posture as qms-mcp-svc-client-secret above; seed.py must not overwrite it with a random value.
- **qms-mcp -> Keycloak (token introspection, RFC 7662)**: value comes from the qms-mcp-svc client Keycloak already provisions (infra/keycloak/terraform's machine_identities for_each) -- fetched live via the Keycloak admin API and recorded here, same posture as tms-mcp-svc-client-secret/rate-mcp-svc-client-secret above; seed.py must not overwrite it with a random value.
- **qms-mcp -> mock-fx**: (credential-level note, shared by every consumer of fx-api-key) qms-mcp's route-cost.normalize tool consults mock-fx directly (real
fx_age_seconds for D2's already-decided freshness gate, then the
real conversion via mock-fx's own /convert) -- reuses the shared
key, same posture as tms-mcp/tms-api-key et al (decision #8).
- **qms-mcp -> mock-qms**: (credential-level note, shared by every consumer of qms-api-key) qms-mcp AND approval-mcp both reuse this shared key as their own
transport credential to mock-qms (M6, same posture tms-mcp/
tms-api-key established) rather than minting a per-MCP-server key
-- decision #8's accepted weaker-than-per-workload-token granularity
for this hop. The two servers sharing mock-qms is only valid under
ADR-002 because their EXPOSED action sets are disjoint (mechanically
checked, see src/qms-mcp/tests/test_adr002_disjointness.py) -- this
shared-key note documents the transport layer, not the authorization
layer, and does not itself relax that requirement.
- **rate-mcp -> Keycloak (token introspection, RFC 7662)**: value comes from the rate-mcp-svc client Keycloak already provisions (infra/keycloak/terraform's machine_identities for_each) -- fetched live via the Keycloak admin API and recorded here, same posture as tms-mcp-svc-client-secret above; seed.py must not overwrite it with a random value.
- **rate-mcp -> mock-rate**: (credential-level note, shared by every consumer of rate-api-key) rate-mcp reuses this shared key as its own transport credential to
mock-rate (M6, same posture tms-mcp/tms-api-key established in M6a)
rather than minting a per-MCP-server key -- decision #8's accepted
weaker-than-per-workload-token granularity for this hop.
- **rfq_common.pdp.PDPClient (every service that authorizes) -> cedar-agent**: cedar-agent is never published on a host port and only reachable over the internal compose network (infra/compose.support.yaml has no cedar-agent service today; the real cedar-agent runs standalone, container_name rfq-showcase-cedar-agent, compose-internal-only). No request credential is checked on POST /v1/is_authorized. Accepted for this showcase's scope because the only callers are this repo's own trusted services on a private network, never an external caller -- same class of deliberate scope call as the shared-API-key transport edges below, not an oversight.
- **tms-mcp -> Keycloak (token introspection, RFC 7662)**: value comes from the tms-mcp-svc client Keycloak already provisions (infra/keycloak/terraform's machine_identities for_each) -- fetched live via the Keycloak admin API and recorded here, same posture as qms-web-client-secret/ops-dashboard-web-client-secret above; seed.py must not overwrite it with a random value.
- **tms-mcp -> mock-tms**: (credential-level note, shared by every consumer of tms-api-key) tms-mcp reuses this shared key as its own transport credential to mock-tms
(M6a) rather than minting a per-MCP-server key -- decision #8's accepted
weaker-than-per-workload-token granularity, already the repo's existing
posture for this hop (unchanged behavior for the other two consumers).
A dedicated tms-mcp-api-key entry remains status:planned below for a
future tightening, not activated by this milestone.
