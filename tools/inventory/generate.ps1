<#
Joins the static-tier inventory sources into one target data model:
  data/inventory/runtime-manifest/summary.json  -- declared_configuration,
    runtime_deployment, network_surfaces (tools/runtime-manifest/generate.ps1)
  data/inventory/sbom/*.spdx.json                -- image + sbom
    (tools/sbom/generate.ps1)
  data/env/environments.yaml                     -- environments[] (top-level,
    alongside services[], NOT per-service -- dev/test/prod's edge/idp/runtime
    choices apply to the whole deployment, not one service)

Join key for services: service's `image` value, mangled the SAME way
tools/sbom/generate.ps1 names its output files ($image -replace '[/:]', '_')
-- one mangling rule, defined once there, reused here instead of
re-deriving it.

Pure transform, no Docker/network calls -- run `just sbom` and
`just runtime-manifest` first; this only reads their output. YAML parsing
via `uv run --with pyyaml` (no PowerShell-native YAML cmdlet), per user's
global CLAUDE.md: always use uv for Python execution.

identity/capabilities/health/observability are NOT in this join -- they
either need a live running stack (health, observability) or a source this
script doesn't read yet (agents/catalog.yaml). Out of scope here on
purpose, not an oversight.
#>

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "../..")
$inventoryDir = Join-Path $repoRoot "data/inventory"
$runtimeManifestFile = Join-Path $inventoryDir "runtime-manifest/summary.json"
$sbomDir = Join-Path $inventoryDir "sbom"
$environmentsFile = Join-Path $repoRoot "data/env/environments.yaml"
$outFile = Join-Path $inventoryDir "services.json"

if (-not (Test-Path $runtimeManifestFile)) {
    Write-Error "missing $runtimeManifestFile -- run 'just runtime-manifest' first"
}
if (-not (Test-Path $sbomDir)) {
    Write-Error "missing $sbomDir -- run 'just sbom' first"
}
if (-not (Test-Path $environmentsFile)) {
    Write-Error "missing $environmentsFile"
}

$runtimeManifest = Get-Content $runtimeManifestFile -Raw | ConvertFrom-Json

function Get-SafeName($image) {
    $image -replace '[/:]', '_'
}

$services = foreach ($svc in $runtimeManifest.services) {
    $safeName = Get-SafeName $svc.image
    $sbomFile = Join-Path $sbomDir "$safeName.spdx.json"

    $sbom = $null
    if (Test-Path $sbomFile) {
        $spdx = Get-Content $sbomFile -Raw | ConvertFrom-Json
        $sbom = [ordered]@{
            path         = "data/inventory/sbom/$safeName.spdx.json"
            package_count = @($spdx.packages).Count
            spdx_version  = $spdx.spdxVersion
        }
    }

    [ordered]@{
        name = $svc.name
        stack = $svc.stack
        declared_configuration = [ordered]@{
            image = $svc.image
            build = $svc.build
        }
        runtime_deployment = [ordered]@{
            ports    = $svc.ports
            volumes  = $svc.volumes
            profiles = $svc.profiles
        }
        network_surfaces = [ordered]@{
            networks = $svc.networks
        }
        image = [ordered]@{
            ref  = $svc.image
            sbom = $sbom
        }
    }
}

$missingSbom = $services | Where-Object { -not $_.image.sbom } | ForEach-Object { $_.declared_configuration.image }
if ($missingSbom) {
    Write-Output "no SBOM found for: $($missingSbom -join ', ') (image not built when 'just sbom' last ran)"
}

# No PowerShell-native YAML cmdlet -- uv run --with pyyaml, same pattern
# already used elsewhere in this repo for ad-hoc YAML->JSON in PowerShell.
$environmentsJson = uv run --with pyyaml python -c "
import json, sys, yaml
with open(sys.argv[1]) as f:
    print(json.dumps(yaml.safe_load(f)))
" $environmentsFile
$environments = ($environmentsJson | ConvertFrom-Json).environments

[ordered]@{
    services     = $services
    environments = $environments
} | ConvertTo-Json -Depth 8 | Out-File -Encoding utf8 $outFile

Write-Output "service inventory written to $outFile"
