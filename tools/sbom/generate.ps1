<#
Generates SPDX-JSON SBOMs via syft's official container (infra/sbom/docker-compose.yml,
pinned anchore/syft:v1.18.0) -- NOT a host-installed syft binary. Same
reasoning as infra/a2a-inspector, infra/mcp-inspector, infra/publishing:
pin the toolchain version in a container, don't depend on whatever happens
to be on PATH on this machine.

Three independent scan modes, all written to data/inventory/sbom/:
  1. One SBOM per showcase-built image (image list read directly from the
     two compose files' `image:` fields -- one source of truth, same
     convention as tools/identity/gen_*.py deriving from the Validated
     Identity Model instead of a hardcoded roster). Images must already be
     built (`docker compose ... build`) -- this only scans what's in the
     local image store, it doesn't build anything.
  2. One SBOM for the repo's own file-based dependency manifests via a
     `dir:` scan. This is the "outside the container" half: host tooling,
     CI scripts, and anything else that never becomes a built image is
     invisible to mode 1 alone.
  3. One SBOM for src/*'s actual Python dependencies. Found live: syft
     (even latest, v1.49.0) has no cataloger for PEP 621 pyproject.toml
     `[project.dependencies]` or uv.lock -- mode 2's dir scan sees these
     services as zero packages. Fix: `uv export` each service's uv.lock to
     a pip-style requirements.txt first (a format syft DOES parse), staged
     in a host temp dir, then scan that. Requires `uv` on PATH (per user's
     global CLAUDE.md: always use uv for Python execution).
#>

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "../..")
$infraDir = Join-Path $repoRoot "infra"
$outDir = Join-Path $repoRoot "data/inventory/sbom"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$composeFile = Join-Path $infraDir "sbom/docker-compose.yml"
$composeArgs = @("compose", "-f", $composeFile, "run", "--rm", "-T", "syft")

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
    Write-Output "scanning image: $image"
    $safeName = $image -replace '[/:]', '_'
    $outFile = "/sbom/$safeName.spdx.json"
    # The syft container reads images from the daemon via the socket
    # mounted in infra/sbom/docker-compose.yml -- same local image store
    # `docker image inspect` above just checked, no separate pull/copy.
    docker @composeArgs $image -o "spdx-json=$outFile"
}

Write-Output "scanning repo sources: dir:/repo"
# Excludes: VCS/build/cache noise that would otherwise dominate the scan
# with irrelevant entries (or, for infra/.buildcache and data/inventory,
# cause the scan to eat its own prior output).
$excludes = @(
    "./.git", "**/.venv", "**/node_modules", "**/__pycache__",
    "**/.terraform", "./infra/.buildcache", "./data/inventory"
) | ForEach-Object { "--exclude", $_ }
docker @composeArgs dir:/repo @excludes -o "spdx-json=/sbom/repo-sources.spdx.json"

Write-Output "exporting python deps: uv export per src/* service"
$stagingDir = Join-Path $env:TEMP "eaop-sbom-python-export"
Remove-Item -Recurse -Force $stagingDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null

$pyServiceDirs = Get-ChildItem -Path (Join-Path $repoRoot "src") -Directory |
    Where-Object { Test-Path (Join-Path $_.FullName "pyproject.toml") }

foreach ($svcDir in $pyServiceDirs) {
    $reqFile = Join-Path $stagingDir "$($svcDir.Name).requirements.txt"
    uv export --project $svcDir.FullName --no-hashes --no-dev -q -o $reqFile 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Output "  skip (uv export failed): $($svcDir.Name)"
    }
}

# Separate host-path volume mount (not part of infra/sbom/docker-compose.yml
# itself) -- staging dir lives outside the repo tree on purpose, so exported
# requirements.txt files never need a .gitignore entry or repo-tree cleanup.
docker compose -f $composeFile run --rm -T -v "${stagingDir}:/staging:ro" syft `
    dir:/staging -o "spdx-json=/sbom/repo-python-deps.spdx.json"

Remove-Item -Recurse -Force $stagingDir -ErrorAction SilentlyContinue

Write-Output "SBOMs written to $outDir"
