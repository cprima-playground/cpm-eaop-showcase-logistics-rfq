variable "tenant_id" {
  type        = string
  description = "Entra tenant id (GUID). rpapubhotmail.onmicrosoft.com's tenant, confirmed reachable this session."
}

variable "seed_password" {
  type        = string
  description = "Initial password for generated users (force-change on first sign-in)."
  sensitive   = true
}
