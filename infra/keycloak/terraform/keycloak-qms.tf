# Human SSO for the QMS frontend -- Authorization Code + PKCE, own client
# (separate from ops-dashboard-web: redirect URIs and the audience mapper
# are both hardcoded per-client, so one client can't back two frontends --
# see keycloak-sso.tf's own client for the same pattern). Kept in its own
# file, not appended to keycloak-sso.tf, so QMS's resources are
# independently reviewable/destroyable.
#
# Roles here are CLIENT roles on qms-web, not realm roles like ops-viewer --
# a deliberate correction: Cedar already authorizes D6 on GROUP membership
# (Agentic::Group::"rfq-commercial-emea"), never on a Keycloak role name.
# These client roles are UI-gating convenience only (what a QMS session
# *sees*), not what Cedar *authorizes* -- the real enforcement point is D19
# (still unmodeled, see mock_qms/api.py's decide_quote_version x-gap).
#
# Same test-only deviation as ops-dashboard-web: direct_access_grants_enabled
# is TRUE so the skip-gated live integration test can mint a token without
# driving a real browser through the PKCE redirect dance. Never enable this
# for a client backing a real deployment.

resource "keycloak_openid_client" "qms_web" {
  realm_id                        = keycloak_realm.rfq.id
  client_id                       = "qms-web"
  name                             = "qms-web"
  access_type                      = "CONFIDENTIAL"
  standard_flow_enabled            = true
  service_accounts_enabled         = false
  direct_access_grants_enabled     = var.enable_test_password_grant # test-only, see deviation note above
  valid_redirect_uris              = var.qms_redirect_uris
  valid_post_logout_redirect_uris  = ["http://localhost:8007", "https://qms.rfq-showcase.localhost"]
  web_origins                      = ["http://localhost:8007", "https://qms.rfq-showcase.localhost"]
}

output "qms_web_client_secret" {
  value     = keycloak_openid_client.qms_web.client_secret
  sensitive = true
}

resource "keycloak_openid_audience_protocol_mapper" "qms_web_audience" {
  realm_id                 = keycloak_realm.rfq.id
  client_id                = keycloak_openid_client.qms_web.id
  name                      = "qms-web-audience"
  included_custom_audience = "qms-web"
}

# Same shape as ops-dashboard's tid/oid/groups/roles mappers (keycloak-sso.tf)
# -- one instance per client, Keycloak protocol mappers are client-scoped.
resource "keycloak_openid_hardcoded_claim_protocol_mapper" "qms_tid" {
  realm_id    = keycloak_realm.rfq.id
  client_id   = keycloak_openid_client.qms_web.id
  name        = "tid"
  claim_name  = "tid"
  claim_value = "rfq-dev-tenant"

  claim_value_type   = "String"
  add_to_id_token     = true
  add_to_access_token = true
}

resource "keycloak_openid_user_attribute_protocol_mapper" "qms_oid" {
  realm_id          = keycloak_realm.rfq.id
  client_id         = keycloak_openid_client.qms_web.id
  name              = "oid"
  user_attribute    = "oid"
  claim_name        = "oid"
  claim_value_type  = "String"

  add_to_id_token     = true
  add_to_access_token = true
}

resource "keycloak_openid_group_membership_protocol_mapper" "qms_groups" {
  realm_id    = keycloak_realm.rfq.id
  client_id   = keycloak_openid_client.qms_web.id
  name        = "groups"
  claim_name  = "groups"
  full_path   = true

  add_to_id_token     = true
  add_to_access_token = true
}

# Intentional inconsistency with ops-dashboard's `roles` mapper
# (keycloak_openid_user_realm_role_protocol_mapper, keycloak-sso.tf): that
# one emits REALM roles ("ops-viewer"); this one emits CLIENT roles scoped
# to qms-web. Both land in the same normalized `roles` claim
# (rfq_common.identity.resolve_principal reads it verbatim either way), but
# the semantics differ by app on purpose -- ops-viewer is genuinely
# cross-cutting (any human, any system), QMS's roles are UI-gating local to
# this one app (see the file header note on why they're client roles).
resource "keycloak_openid_user_client_role_protocol_mapper" "qms_roles" {
  realm_id                = keycloak_realm.rfq.id
  client_id                = keycloak_openid_client.qms_web.id
  client_id_for_role_mappings = keycloak_openid_client.qms_web.client_id
  name                     = "roles"
  claim_name               = "roles"
  multivalued              = true

  add_to_id_token     = true
  add_to_access_token = true
}

# New claims this session's design needs, not present on ops-dashboard's
# client -- same shape as oid, just two more user attributes.
resource "keycloak_openid_user_attribute_protocol_mapper" "qms_approval_limit" {
  realm_id          = keycloak_realm.rfq.id
  client_id         = keycloak_openid_client.qms_web.id
  name              = "approval_limit_eur_cents"
  user_attribute    = "approval_limit_eur_cents"
  claim_name        = "approval_limit_eur_cents"
  claim_value_type  = "String" # stored/emitted as string, parsed as int in mock_qms -- same precedent as oid

  add_to_id_token     = true
  add_to_access_token = true
}

resource "keycloak_openid_user_attribute_protocol_mapper" "qms_manager" {
  realm_id          = keycloak_realm.rfq.id
  client_id         = keycloak_openid_client.qms_web.id
  name              = "manager"
  user_attribute    = "manager"
  claim_name        = "manager"
  claim_value_type  = "String"

  add_to_id_token     = true
  add_to_access_token = true
}

# --- Client roles (qms-web) -- UI-gating only, see file header note -------
resource "keycloak_role" "qms_reader" {
  realm_id  = keycloak_realm.rfq.id
  client_id = keycloak_openid_client.qms_web.id
  name      = "reader"
}

resource "keycloak_role" "qms_commercial_manager" {
  realm_id  = keycloak_realm.rfq.id
  client_id = keycloak_openid_client.qms_web.id
  name      = "commercial-manager"
}

resource "keycloak_role" "qms_pricing_manager" {
  realm_id  = keycloak_realm.rfq.id
  client_id = keycloak_openid_client.qms_web.id
  name      = "pricing-manager"
}

resource "keycloak_role" "qms_administrator" {
  realm_id  = keycloak_realm.rfq.id
  client_id = keycloak_openid_client.qms_web.id
  name      = "administrator"
}

# --- Groups (canonical, generator-owned; M3.2a) ----------------------------
# rfq-commercial-emea/rfq-pricing-emea now for_each over
# keycloak.generated.tfvars.json (tools/identity/gen_keycloak.py), reuses the
# exact names Cedar already references (authorization/policies.cedar's
# Agentic::Group::"rfq-commercial-emea"), flat (no nesting -- Cedar keys off
# the plain group name, not a Keycloak path; identity/actors.yaml's own
# `path:` field is a separate, cosmetic org attribute).
#
# rfq_qms_platform stays hand-authored below -- MIGRATION.md's Ambiguous
# classification (aiden.ashford's live group isn't in identity/groups.yaml's
# 9-group model).
locals {
  keycloak_generated = jsondecode(file("${path.module}/keycloak.generated.tfvars.json"))
}

resource "keycloak_group" "groups" {
  for_each = { for g in local.keycloak_generated.groups : g.group_id => g }
  realm_id = keycloak_realm.rfq.id
  name     = each.value.group_id
}

moved {
  from = keycloak_group.rfq_commercial_emea
  to   = keycloak_group.groups["rfq-commercial-emea"]
}

moved {
  from = keycloak_group.rfq_pricing_emea
  to   = keycloak_group.groups["rfq-pricing-emea"]
}

resource "keycloak_group" "rfq_qms_platform" {
  realm_id = keycloak_realm.rfq.id
  name     = "rfq-qms-platform"
}

# --- Users (canonical, generator-owned; M3.2a) ------------------------------
# diane.delgado/mona.commercial/sam.pricing now for_each over the same
# generated input. Roles stay hand-authored per-user below (MIGRATION.md:
# no job_title/department -> Keycloak role projection rule exists) -- only
# their `user_id` reference is updated to the new for_each address.
resource "keycloak_user" "humans" {
  for_each   = { for u in local.keycloak_generated.users : u.username => u }
  depends_on = [null_resource.enable_unmanaged_attributes]
  realm_id   = keycloak_realm.rfq.id
  username   = each.value.username
  email      = each.value.email
  enabled    = true
  first_name = each.value.first_name
  last_name  = each.value.last_name

  attributes = each.value.attributes

  initial_password {
    value     = var.keycloak_user_password
    temporary = false
  }
}

moved {
  from = keycloak_user.diane_delgado
  to   = keycloak_user.humans["diane.delgado"]
}

moved {
  from = keycloak_user.mona_commercial
  to   = keycloak_user.humans["mona.commercial"]
}

moved {
  from = keycloak_user.sam_pricing
  to   = keycloak_user.humans["sam.pricing"]
}

resource "keycloak_user_roles" "diane_delgado_roles" {
  realm_id = keycloak_realm.rfq.id
  user_id  = keycloak_user.humans["diane.delgado"].id
  role_ids = [keycloak_role.qms_reader.id]
}

resource "keycloak_user_roles" "mona_commercial_roles" {
  realm_id = keycloak_realm.rfq.id
  user_id  = keycloak_user.humans["mona.commercial"].id
  role_ids = [keycloak_role.qms_reader.id, keycloak_role.qms_commercial_manager.id]
}

resource "keycloak_user_roles" "sam_pricing_roles" {
  realm_id = keycloak_realm.rfq.id
  user_id  = keycloak_user.humans["sam.pricing"].id
  role_ids = [keycloak_role.qms_reader.id, keycloak_role.qms_pricing_manager.id]
}

# human_group_memberships: keyed by username, assumes at most one group per
# human (true for every migrated human today -- MIGRATION.md's known
# limitation).
resource "keycloak_user_groups" "human_group_memberships" {
  for_each  = { for m in local.keycloak_generated.group_memberships : m.username => m }
  realm_id  = keycloak_realm.rfq.id
  user_id   = keycloak_user.humans[each.value.username].id
  group_ids = [keycloak_group.groups[each.value.group_id].id]
}

moved {
  from = keycloak_user_groups.mona_commercial_groups
  to   = keycloak_user_groups.human_group_memberships["mona.commercial"]
}

moved {
  from = keycloak_user_groups.sam_pricing_groups
  to   = keycloak_user_groups.human_group_memberships["sam.pricing"]
}

resource "keycloak_user" "aiden_ashford" {
  depends_on = [null_resource.enable_unmanaged_attributes]
  realm_id   = keycloak_realm.rfq.id
  username   = "aiden.ashford"
  email      = "aiden.ashford@rfq-showcase.dev"
  enabled    = true
  first_name = "Aiden"
  last_name  = "Ashford"

  attributes = tomap({ oid = "8e41c2b0-0000-4000-9000-000000000013" })

  initial_password {
    value     = var.keycloak_user_password
    temporary = false
  }
}

resource "keycloak_user_roles" "aiden_ashford_roles" {
  realm_id = keycloak_realm.rfq.id
  user_id  = keycloak_user.aiden_ashford.id
  role_ids = [keycloak_role.qms_reader.id, keycloak_role.qms_administrator.id]
}

resource "keycloak_user_groups" "aiden_ashford_groups" {
  realm_id  = keycloak_realm.rfq.id
  user_id   = keycloak_user.aiden_ashford.id
  group_ids = [keycloak_group.rfq_qms_platform.id]
}
