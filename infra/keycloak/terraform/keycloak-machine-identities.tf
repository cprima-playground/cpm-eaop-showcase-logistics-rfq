# Machine-identity clients (3 agents + 4 MCP-server workloads) -- M3.2b,
# net-new, none existed in .tf before this. Canonical, generator-owned:
# for_each over keycloak.generated.tfvars.json (tools/identity/
# gen_keycloak.py), sourced from identity/actors.yaml + identity/
# projections/keycloak.yaml's client_id naming. Own file, not appended to
# keycloak-qms.tf/keycloak-sso.tf, so machine identities are independently
# reviewable/destroyable from the two human-SSO clients (same convention
# those files' own headers state).
#
# service_accounts_enabled = true, standard_flow_enabled = false:
# client-credentials grant only, no interactive login -- these are the
# workload/agent identities spikes/mcp/authenticated-server's
# MCP_INTROSPECTION_CLIENT_ID pattern and agents/catalog.yaml's
# caller_identity.keycloak_client already assume exist.
resource "keycloak_openid_client" "machine_identities" {
  for_each                  = { for c in local.keycloak_generated.clients : c.client_id => c }
  realm_id                   = keycloak_realm.rfq.id
  client_id                  = each.value.client_id
  name                        = each.value.client_id
  access_type                 = "CONFIDENTIAL"
  standard_flow_enabled       = false
  service_accounts_enabled    = each.value.service_account_enabled
  direct_access_grants_enabled = false
}

# Keycloak-generated, not seedable by seed.py -- identity/credentials-inventory.yaml
# marks all 7 of these `seed: false` with vault_path == "rfq/${client_id}-client-secret".
# Found live: nothing ever pushed these to Vault (only the 2 *web* client
# secrets had a push script), so every workload's run_startup_self_check()
# hung/failed identically on every `just up` -- containers showed "Up" but
# never bound their port, no logs, no crash. push-web-secrets-to-vault.ps1
# reads this output and pushes each one under its credentials-inventory path.
output "machine_identity_client_secrets" {
  value     = { for k, c in keycloak_openid_client.machine_identities : k => c.client_secret }
  sensitive = true
}
