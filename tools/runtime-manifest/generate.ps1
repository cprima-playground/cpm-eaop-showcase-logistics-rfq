<#
Generates the RUNTIME leg of the project inventory (SOURCE + BUILD are
covered by tools/sbom/generate.ps1 via syft; syft has no notion of
services/ports/volumes/networks -- that's what this script derives).

Source of truth: `docker compose config --format json` for each of the
three compose projects this repo runs. Compose has already resolved
.env values, profiles, and anchors by the time it prints this -- reading
it beats re-parsing the raw yaml files by hand and risking drift.

Not a build step: doesn't need images built, just the compose files.
#>

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "../..")
$infraDir = Join-Path $repoRoot "infra"
$outDir = Join-Path $repoRoot "data/inventory/runtime-manifest"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$envFile = "--env-file", (Join-Path $repoRoot ".env")

$stacks = @(
    @{ name = "eaop-infra"; project = "eaop-infra"; files = @("compose.support.yaml") }
    @{ name = "eaop-logistics"; project = "eaop-logistics"; files = @("compose.showcase.yaml") }
    @{ name = "eaop-observability"; project = "eaop-infra"; files = @("observability/docker-compose.yml") }
)

foreach ($stack in $stacks) {
    $fileArgs = $stack.files | ForEach-Object { "-f", (Join-Path $infraDir $_) }
    Write-Output "resolving: $($stack.name)"
    $outFile = Join-Path $outDir "$($stack.name).compose.json"
    docker compose @envFile -p $stack.project @fileArgs config --format json | Out-File -Encoding utf8 $outFile
}

# Fold the three resolved configs into one flat services/ports/volumes/networks
# summary -- the per-stack files above are the full fidelity source, this is
# the "what actually runs, one screen" view.
$summary = [ordered]@{ services = @(); volumes = @(); networks = @() }
foreach ($stack in $stacks) {
    $cfg = Get-Content (Join-Path $outDir "$($stack.name).compose.json") -Raw | ConvertFrom-Json
    foreach ($svcName in $cfg.services.PSObject.Properties.Name) {
        $svc = $cfg.services.$svcName
        $summary.services += [ordered]@{
            stack      = $stack.name
            name       = $svcName
            image      = $svc.image
            build      = if ($svc.build) { $svc.build.context } else { $null }
            ports      = @($svc.ports | Where-Object { $_.published -or $_.target } | ForEach-Object { "$($_.published):$($_.target)" })
            volumes    = @($svc.volumes | ForEach-Object { $_.source ? "$($_.source):$($_.target)" : $_.target })
            networks   = @($svc.networks.PSObject.Properties.Name)
            profiles   = if ($svc.profiles) { @($svc.profiles) } else { @() }
        }
    }
    if ($cfg.volumes) {
        foreach ($volName in $cfg.volumes.PSObject.Properties.Name) {
            $summary.volumes += [ordered]@{ stack = $stack.name; name = $volName; external = [bool]$cfg.volumes.$volName.external }
        }
    }
    if ($cfg.networks) {
        foreach ($netName in $cfg.networks.PSObject.Properties.Name) {
            $summary.networks += [ordered]@{ stack = $stack.name; name = $netName; external = [bool]$cfg.networks.$netName.external }
        }
    }
}
$summaryFile = Join-Path $outDir "summary.json"
$summary | ConvertTo-Json -Depth 6 | Out-File -Encoding utf8 $summaryFile

Write-Output "runtime manifest written to $outDir"
