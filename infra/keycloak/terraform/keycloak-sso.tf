# Human SSO for the ops-dashboard -- Authorization Code + PKCE, backing an
# interactive login (see identity/claims-contract.md, ops_dashboard/sso.py).
# Deliberately shapes claims to resemble what Entra would issue (tid, oid,
# groups, roles) so rfq_common's claims-contract normalization stays the same
# regardless of which real IdP eventually replaces Keycloak (test/prod: Entra,
# per deploy/environments.md).
#
# Deviation from cpm-eaop's control-panel-web client: direct_access_grants_enabled
# is TRUE here (ROPC/password grant). This exists ONLY so the skip-gated live
# integration test (ops-dashboard/tests/test_sso_integration.py) can mint a
# token for a known test user without driving a real browser through the PKCE
# redirect dance. Never enable this for a client backing a real deployment.

resource "keycloak_openid_client" "ops_dashboard_web" {
  realm_id                     = keycloak_realm.rfq.id
  client_id                    = "ops-dashboard-web"
  name                          = "ops-dashboard-web"
  access_type                   = "CONFIDENTIAL"
  standard_flow_enabled         = true
  service_accounts_enabled      = false
  direct_access_grants_enabled  = var.enable_test_password_grant # see deviation note above -- test-only
  valid_redirect_uris            = var.ops_dashboard_redirect_uris
  valid_post_logout_redirect_uris = ["http://localhost:8006", "https://ops-dashboard.rfq-showcase.localhost"]
  web_origins                    = ["http://localhost:8006", "https://ops-dashboard.rfq-showcase.localhost"]
}

output "ops_dashboard_web_client_secret" {
  value     = keycloak_openid_client.ops_dashboard_web.client_secret
  sensitive = true
}

# Keycloak's default access token carries no usable `aud` for this client --
# rfq_common.verify()'s audience check needs one. Map the client's own id in
# explicitly (same fix cpm-eaop applies to its client-credentials client).
resource "keycloak_openid_audience_protocol_mapper" "ops_dashboard_audience" {
  realm_id                 = keycloak_realm.rfq.id
  client_id                 = keycloak_openid_client.ops_dashboard_web.id
  name                      = "ops-dashboard-audience"
  included_custom_audience = "ops-dashboard-web"
}

# tid: Entra's tenant id. Hardcoded -- a single Keycloak realm has no
# multi-tenant concept, so this is a constant standing in for "which tenant."
resource "keycloak_openid_hardcoded_claim_protocol_mapper" "tid" {
  realm_id    = keycloak_realm.rfq.id
  client_id   = keycloak_openid_client.ops_dashboard_web.id
  name        = "tid"
  claim_name  = "tid"
  claim_value = "rfq-dev-tenant"

  claim_value_type   = "String"
  add_to_id_token     = true
  add_to_access_token = true
}

resource "keycloak_openid_user_attribute_protocol_mapper" "oid" {
  realm_id          = keycloak_realm.rfq.id
  client_id         = keycloak_openid_client.ops_dashboard_web.id
  name              = "oid"
  user_attribute    = "oid"
  claim_name        = "oid"
  claim_value_type  = "String"

  add_to_id_token     = true
  add_to_access_token = true
}

resource "keycloak_openid_group_membership_protocol_mapper" "groups" {
  realm_id    = keycloak_realm.rfq.id
  client_id   = keycloak_openid_client.ops_dashboard_web.id
  name        = "groups"
  claim_name  = "groups"
  full_path   = true

  add_to_id_token     = true
  add_to_access_token = true
}

resource "keycloak_openid_user_realm_role_protocol_mapper" "roles" {
  realm_id     = keycloak_realm.rfq.id
  client_id    = keycloak_openid_client.ops_dashboard_web.id
  name         = "roles"
  claim_name   = "roles"
  multivalued  = true

  add_to_id_token     = true
  add_to_access_token = true
}

# Minimal role/group set -- just enough to prove role-gating end to end.
# NOT the full enterprise identity/groups.yaml buildout (a separate,
# larger TODO item) -- see build-plan.md's ops-dashboard entry.
resource "keycloak_role" "ops_viewer" {
  realm_id = keycloak_realm.rfq.id
  name     = "ops-viewer"
}

resource "keycloak_group" "ops_team" {
  realm_id = keycloak_realm.rfq.id
  name     = "Ops"
}

# alice: has the ops-viewer role -- can see the dashboard.
resource "keycloak_user" "alice" {
  depends_on = [null_resource.enable_unmanaged_attributes]
  realm_id   = keycloak_realm.rfq.id
  username   = "alice"
  email      = "alice@rfq-showcase.dev"
  enabled    = true
  first_name = "Alice"
  last_name  = "Ops"

  attributes = tomap({ oid = "8e41c2b0-0000-4000-9000-000000000001" })

  initial_password {
    value     = var.keycloak_user_password
    temporary = false
  }
}

resource "keycloak_user_roles" "alice_roles" {
  realm_id = keycloak_realm.rfq.id
  user_id  = keycloak_user.alice.id
  role_ids = [keycloak_role.ops_viewer.id]
}

resource "keycloak_user_groups" "alice_groups" {
  realm_id  = keycloak_realm.rfq.id
  user_id   = keycloak_user.alice.id
  group_ids = [keycloak_group.ops_team.id]
}

# bob: logged-in, but no ops-viewer role -- proves the 403 role-gate path.
resource "keycloak_user" "bob" {
  depends_on = [null_resource.enable_unmanaged_attributes]
  realm_id   = keycloak_realm.rfq.id
  username   = "bob"
  email      = "bob@rfq-showcase.dev"
  enabled    = true
  first_name = "Bob"
  last_name  = "NoAccess"

  attributes = tomap({ oid = "8e41c2b0-0000-4000-9000-000000000002" })

  initial_password {
    value     = var.keycloak_user_password
    temporary = false
  }
}
