variable "keycloak_url" {
  type        = string
  description = "Base URL of the local Keycloak instance (infra/keycloak/docker-compose.yml)"
  default     = "http://localhost:8081"
}

variable "keycloak_admin_username" {
  type        = string
  description = "Keycloak admin username (infra/keycloak/docker-compose.yml)"
  default     = "admin"
}

variable "keycloak_admin_password" {
  type        = string
  description = "Keycloak admin password (infra/keycloak/docker-compose.yml -- fixed dev value)"
  default     = "rfq-dev-admin"
  sensitive   = true
}

variable "keycloak_user_password" {
  type        = string
  description = "Shared password for the sandbox test users -- fine for a dev demo identity, not for anything real"
  default     = "rfq-dev-user"
  sensitive   = true
}

variable "ops_dashboard_redirect_uris" {
  type        = list(string)
  description = "Valid redirect URIs for the ops-dashboard-web Auth-Code+PKCE client -- direct (:8006) and via the local Caddy edge (infra/caddy, preferred)"
  default = [
    "http://localhost:8006/callback",
    "https://ops-dashboard.rfq-showcase.localhost/callback",
  ]
}
