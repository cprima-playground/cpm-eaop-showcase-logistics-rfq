variable "project_id" {
  description = "GCP project this repo's spikes deploy to."
  type        = string
  default     = "cpm-geap-2026"
}

variable "region" {
  description = "Default region. hello-agent-adk and hello-mcp both used us-central1."
  type        = string
  default     = "us-central1"
}
