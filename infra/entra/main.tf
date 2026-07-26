# Entra (Azure AD) provisioning — M3.3. Ported PATTERN from cpm-eaop's
# infra/entra (not shared state/tenant creds — this is showcase's own
# module, generator-driven via for_each instead of single hardcoded
# resources). Directory-only: needs a tenant + `az login`, no Azure
# subscription. Free/personal-tenant safe: assigned membership only (no
# dynamic groups / P1), same constraint cpm-eaop's module documented.
#
# State is local and gitignored. Same tenant as cpm-eaop's proof
# (rpapubhotmail.onmicrosoft.com, confirmed reachable via `terraform plan`
# 2026-07-25, project memory) — reused, not re-created.
#
# Run:  az login --allow-no-subscriptions --tenant <TENANT_ID>
#       uv run --with pydantic --with pyyaml python -m tools.identity.write_entra_tfvars
#       terraform init
#       terraform plan  -var-file=terraform.tfvars
#       terraform apply -var-file=terraform.tfvars

terraform {
  required_providers {
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
  }
}

provider "azuread" {
  tenant_id = var.tenant_id
}

data "azuread_client_config" "current" {}

locals {
  entra_generated = jsondecode(file("${path.module}/entra.generated.tfvars.json"))
}

# --- Humans ------------------------------------------------------------
resource "azuread_user" "humans" {
  for_each              = { for u in local.entra_generated.users : u.upn => u }
  user_principal_name   = each.value.upn
  display_name          = each.value.display_name
  mail_nickname         = split("@", each.value.upn)[0]
  password              = var.seed_password
  force_password_change = true
  account_enabled       = true
}

# --- Groups (assigned membership only -- free-tier constraint) ---------
resource "azuread_group" "groups" {
  for_each         = { for g in local.entra_generated.groups : g.group_id => g }
  display_name     = each.value.group_id
  security_enabled = true
}

resource "azuread_group_member" "human_group_memberships" {
  for_each          = { for m in local.entra_generated.group_memberships : m.upn => m }
  group_object_id   = azuread_group.groups[each.value.group_id].object_id
  member_object_id  = azuread_user.humans[each.value.upn].object_id
}

# --- Machine identities (3 agents + 4 workloads) — client-credentials --
# No public_client/oauth2_permission_scope block: these are service-to-
# service identities, not interactive delegated flows (cpm-eaop's
# explore-app is the delegated-flow pattern; this is the app-only one,
# same shape as its azuread_application_password.explore secret).
resource "azuread_application" "machine_identities" {
  for_each         = { for a in local.entra_generated.app_registrations : a.display_name => a }
  display_name     = each.value.display_name
  identifier_uris  = ["api://${var.tenant_id}/${each.value.display_name}"]
  sign_in_audience = "AzureADMyOrg"
}

resource "azuread_service_principal" "machine_identities" {
  for_each  = azuread_application.machine_identities
  client_id = each.value.client_id
}

# Credential lifecycle (identity/README.md's "Machine credentials are a
# runtime concern" section): this is the ONLY resource that changes on
# rotation. azuread_application/azuread_service_principal above (canonical
# id, client_id) are separate resources -- rotating a secret here can
# never touch them, structurally, not just by convention.
resource "azuread_application_password" "machine_identities" {
  for_each        = azuread_application.machine_identities
  application_id  = each.value.id
  display_name    = "generated-secret"
  end_date        = "2026-10-23T00:00:00Z"
}
