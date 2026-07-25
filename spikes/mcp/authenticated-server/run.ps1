$ErrorActionPreference = "Stop"

$terraformDirectory = Join-Path $PSScriptRoot "../../../infra/keycloak/terraform"
Push-Location $terraformDirectory
try {
    $secret = (terraform output -raw qms_web_client_secret).Trim()
}
finally {
    Pop-Location
}

if ([string]::IsNullOrWhiteSpace($secret)) {
    throw "No qms_web_client_secret found. Run terraform init/apply in infra/keycloak/terraform first."
}

$env:MCP_INTROSPECTION_CLIENT_ID = "qms-web"
$env:MCP_INTROSPECTION_CLIENT_SECRET = $secret

docker compose up --build -d
