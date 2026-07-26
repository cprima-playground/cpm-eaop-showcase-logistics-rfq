# Human SSO app for interactive login against Entra -- mirrors
# infra/keycloak/terraform/keycloak-sso.tf's ops-dashboard-web client
# (same app-role/groups-claim shape) so rfq_common's Entra claim adapter
# (tmp/oidc-identity-unification-plan.md, Decision 4) can be verified
# against a REAL signed-in human token instead of guessed by analogy with
# the machine-identity (client-credentials) path, which was already proven.
#
# public_client + fallback_public_client_enabled: needed for ROPC
# (resource-owner password grant) so a skip-gated test can mint a token
# for a known fixture user without driving a real browser through the
# authorization-code/PKCE redirect dance -- same deviation, same reason,
# as keycloak-sso.tf's direct_access_grants_enabled.
resource "azuread_application" "ops_dashboard_web" {
  display_name     = "ops-dashboard-web"
  identifier_uris  = ["api://${var.tenant_id}/ops-dashboard-web"]
  sign_in_audience = "AzureADMyOrg"

  group_membership_claims = ["SecurityGroup"]

  api {
    requested_access_token_version = 2

    oauth2_permission_scope {
      id                          = "ef129bde-e632-4744-ac1e-6c7134a1fa7a"
      admin_consent_description  = "Allow the app to access ops-dashboard-web on behalf of the signed-in user."
      admin_consent_display_name = "Access ops-dashboard-web"
      user_consent_description   = "Allow the app to access ops-dashboard-web on your behalf."
      user_consent_display_name  = "Access ops-dashboard-web"
      value                      = "user_impersonation"
      type                       = "User"
      enabled                    = true
    }
  }

  app_role {
    id                   = "7097df6f-3acc-4ca9-b2c4-a6127b8f3f1a"
    allowed_member_types = ["User"]
    display_name         = "Ops Viewer"
    description          = "Can view the ops dashboard."
    value                = "ops-viewer"
    enabled              = true
  }

  public_client {
    redirect_uris = ["http://localhost"]
  }

  fallback_public_client_enabled = true
}

resource "azuread_service_principal" "ops_dashboard_web" {
  client_id = azuread_application.ops_dashboard_web.client_id
}

# mona.commercial: reuse the already-provisioned fixture human (same one
# test_pep.py's human-path tests already use), assign the ops-viewer role --
# mirrors keycloak-sso.tf's alice/ops-viewer assignment.
resource "azuread_app_role_assignment" "mona_ops_viewer" {
  app_role_id         = one([for r in azuread_application.ops_dashboard_web.app_role : r.id if r.value == "ops-viewer"])
  principal_object_id = azuread_user.humans["mona.commercial@rpapubhotmail.onmicrosoft.com"].object_id
  resource_object_id  = azuread_service_principal.ops_dashboard_web.object_id
}

output "ops_dashboard_web_client_id" {
  value = azuread_application.ops_dashboard_web.client_id
}
