# The realm itself. Single realm for the whole showcase's dev-local human SSO
# (mirrors cpm-eaop's approach: one Keycloak sandbox realm standing in for an
# eventual real IdP -- Entra in test/prod, per deploy/environments.md).
resource "keycloak_realm" "rfq" {
  realm   = "rfq"
  enabled = true
}

# Keycloak 24+ enforces a declarative "User Profile" -- any user attribute not
# explicitly declared there (e.g. our custom "oid") is silently DROPPED on
# write, not rejected -- easy to miss (terraform apply reports success; the
# claim just never shows up in a token). The mrparkers/keycloak provider (4.4)
# has no resource for the User Profile config, so this is a raw admin-API
# PATCH via local-exec, run once per realm creation, before any user that
# needs a custom attribute.
resource "null_resource" "enable_unmanaged_attributes" {
  depends_on = [keycloak_realm.rfq]

  triggers = {
    realm = keycloak_realm.rfq.id
  }

  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = <<-EOT
      set -euo pipefail
      token=$(curl -sf -X POST "${var.keycloak_url}/realms/master/protocol/openid-connect/token" \
        -d "grant_type=password" -d "client_id=admin-cli" \
        -d "username=${var.keycloak_admin_username}" -d "password=${var.keycloak_admin_password}" \
        | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
      profile=$(curl -sf -H "Authorization: Bearer $token" "${var.keycloak_url}/admin/realms/rfq/users/profile")
      patched=$(python -c "import json,sys; d=json.loads(sys.argv[1]); d['unmanagedAttributePolicy']='ENABLED'; print(json.dumps(d))" "$profile")
      curl -sf -X PUT -H "Authorization: Bearer $token" -H "Content-Type: application/json" \
        -d "$patched" "${var.keycloak_url}/admin/realms/rfq/users/profile" > /dev/null
    EOT
  }
}
