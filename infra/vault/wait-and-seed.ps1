<#
Waits for Vault's dev-mode listener to answer, then runs seed.py. Called
from `just up` -- `docker compose up -d` returns as soon as the container
STARTS, not once Vault is actually listening, and vault has no compose
healthcheck to depend_on. Found live: `just up` left showcase services
502'ing because they hit Vault before it was ready and never retried
(secrets are fetched once at service startup, not lazily).
#>

$ErrorActionPreference = "Stop"

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        Invoke-RestMethod -Uri "http://localhost:8200/v1/sys/health" -TimeoutSec 2 -ErrorAction Stop | Out-Null
        $ready = $true
        break
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $ready) {
    Write-Error "vault did not become ready after 30s"
}

Push-Location $PSScriptRoot
try {
    uv run seed.py
} finally {
    Pop-Location
}
