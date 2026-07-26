<#
Generates one SPDX-JSON SBOM per showcase-built image, via syft (must be on
PATH -- not vendored, not a container: a local static binary, same as any
other dev-machine tool this repo assumes, like `docker` or `terraform`).

Image list is read directly from the two compose files' `image:` fields
(infra/compose.support.yaml + infra/compose.showcase.yaml) -- one source of
truth, no separate list to keep in sync by hand, same convention as
tools/identity/gen_*.py deriving from the Validated Identity Model instead
of a hardcoded roster.

Images must already be built (`docker compose ... build`) -- this only
scans what's in the local image store, it doesn't build anything.
#>

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "../..")
$infraDir = Join-Path $repoRoot "infra"
$outDir = Join-Path $repoRoot "data/sbom"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$composeFiles = @("compose.support.yaml", "compose.showcase.yaml") | ForEach-Object { Join-Path $infraDir $_ }

$images = foreach ($file in $composeFiles) {
    Select-String -Path $file -Pattern '^\s*image:\s*(\S+)\s*$' | ForEach-Object { $_.Matches[0].Groups[1].Value }
}
$images = $images | Sort-Object -Unique

foreach ($image in $images) {
    docker image inspect $image *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Output "skip (not built): $image"
        continue
    }
    Write-Output "scanning: $image"
    $safeName = $image -replace '[/:]', '_'
    $outFile = Join-Path $outDir "$safeName.spdx.json"
    syft $image -o spdx-json > $outFile
}

Write-Output "SBOMs written to $outDir"
