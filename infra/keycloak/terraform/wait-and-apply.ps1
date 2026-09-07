<#
Waits for Keycloak's master realm to answer, then applies this terraform
config. Called from `just seed-identity` -- same race as Vault's
wait-and-seed.ps1 (infra/vault/): `docker compose up -d` returns once the
container STARTS, not once Keycloak has finished booting (which takes
longer than Vault's dev-mode instant start), and keycloak has no compose
healthcheck to depend_on.
#>

$ErrorActionPreference = "Stop"

# 180s, not 60s -- found live: a cold/rebuilt Keycloak image needs ~70s just
# for Quarkus augmentation before it even starts booting, then another ~35s
# to finish booting. A 60s budget aborted this whole recipe before Keycloak
# was ready, which meant `just up` never even reached the showcase stack's
# `docker compose up` (the next line in the `up` recipe) -- containers
# stayed on the old 6-of-15 `core` set with no visible error pointing here.
$ready = $false
for ($i = 0; $i -lt 180; $i++) {
    try {
        Invoke-RestMethod -Uri "http://localhost:8081/realms/master/.well-known/openid-configuration" -TimeoutSec 2 -ErrorAction Stop | Out-Null
        $ready = $true
        break
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $ready) {
    Write-Error "keycloak did not become ready after 180s"
}

Push-Location $PSScriptRoot
try {
    terraform init -input=false
    terraform apply -auto-approve
    & "$PSScriptRoot/push-web-secrets-to-vault.ps1"
} finally {
    Pop-Location
}
