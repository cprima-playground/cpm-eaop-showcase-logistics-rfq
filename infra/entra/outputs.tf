output "authenticated_tenant" {
  description = "Tenant the provider is actually acting on -- verify this is the hotmail tenant."
  value       = data.azuread_client_config.current.tenant_id
}

output "user_object_ids" {
  value = { for k, u in azuread_user.humans : k => u.object_id }
}

output "group_object_ids" {
  value = { for k, g in azuread_group.groups : k => g.object_id }
}

output "machine_identity_client_ids" {
  value = { for k, a in azuread_application.machine_identities : k => a.client_id }
}

output "machine_identity_client_secrets" {
  value     = { for k, p in azuread_application_password.machine_identities : k => p.value }
  sensitive = true
}
