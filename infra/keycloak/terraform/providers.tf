# Local-only: provisions the dev Keycloak realm/client/users for the
# ops-dashboard's human SSO login. Distinct from the future infra/terraform/
# (reserved for GCP -- Cloud Run/Apigee/WIF/Secret Manager, per infra/README.md).
terraform {
  required_version = ">= 1.5"

  required_providers {
    keycloak = {
      source  = "mrparkers/keycloak"
      version = "~> 4.4"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
  }

  backend "local" {
    path = "terraform.tfstate"
  }
}

provider "keycloak" {
  client_id = "admin-cli"
  username  = var.keycloak_admin_username
  password  = var.keycloak_admin_password
  url       = var.keycloak_url
}
