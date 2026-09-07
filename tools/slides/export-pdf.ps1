<#
Exports the reveal.js decks listed in data/publishing/manifests.yaml's
`slides:` section to PDF via decktape. Output filename = <Prefix>-<slide
key>.pdf, written to data/slides/pdf/ (canonical generated-artifact copy,
matching tools/sbom/generate.ps1) AND copied into web/downloads/ (gateway-
served, becomes the actual download link on the site).

Usage: pwsh tools/slides/export-pdf.ps1 [-Prefix eaop-logistics] [-OutDir data/slides/pdf] [-WebOutDir web/downloads] [-Port 8123]
#>
param(
    [string]$Prefix = "eaop-logistics",
    [string]$OutDir = "data/slides/pdf",
    [string]$WebOutDir = "web/downloads",
    [int]$Port = 8123
)

$ErrorActionPreference = "Stop"

$repoRoot = (& git rev-parse --show-toplevel 2>$null)
if (-not $repoRoot) { $repoRoot = (Resolve-Path "$PSScriptRoot/../..").Path }
Set-Location $repoRoot

$manifestPath = Join-Path $repoRoot "data/publishing/manifests.yaml"
if (-not (Test-Path $manifestPath)) {
    Write-Error "Manifest not found: $manifestPath"
    exit 1
}

# PowerShell has no built-in YAML parser -- shell out to uv (already a repo
# dependency, pyyaml installed on the fly via --with, no separate venv) to
# convert the manifest to JSON, which ConvertFrom-Json can read natively.
$manifestJson = uv run --with pyyaml python -c "
import json, sys, yaml
with open(sys.argv[1], encoding='utf-8') as f:
    data = yaml.safe_load(f)
print(json.dumps(data.get('slides', {})))
" $manifestPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to read manifest via uv/pyyaml"
    exit 1
}
$slides = $manifestJson | ConvertFrom-Json -AsHashtable
if (-not $slides -or $slides.Count -eq 0) {
    Write-Error "No slides defined in $manifestPath"
    exit 1
}

$outPath = Join-Path $repoRoot $OutDir
New-Item -ItemType Directory -Force -Path $outPath | Out-Null

$webOutPath = Join-Path $repoRoot $WebOutDir
New-Item -ItemType Directory -Force -Path $webOutPath | Out-Null

Write-Host "Starting static server on port $Port (serving ./web)..."
# -FilePath "npx" uses Windows ShellExecute resolution, not PowerShell's own
# command resolution -- it finds npx.ps1 (npm's Windows shim) on PATH and
# launches it via .ps1's default OS handler (Notepad, since Windows
# deliberately doesn't register PowerShell as the double-click handler for
# .ps1 -- security default), instead of running it as a script. Found live.
# Routing through cmd.exe forces resolution of the .cmd shim instead, which
# Windows executes correctly via PATHEXT.
$server = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "npx", "-y", "http-server", "web", "-p", "$Port", "-s" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 2

$failed = @()
try {
    foreach ($key in $slides.Keys) {
        $slide = $slides[$key]
        $relFile = $slide.file
        $title = $slide.title
        $srcPath = Join-Path $repoRoot $relFile
        if (-not (Test-Path $srcPath)) {
            Write-Warning "$key`: source not found: $relFile"
            $failed += $key
            continue
        }

        $filename = "$Prefix-$key.pdf"
        $outFile = Join-Path $outPath $filename
        $deckName = Split-Path $relFile -Leaf
        $url = "http://localhost:$Port/slides/$deckName"

        Write-Host "Exporting '$title' ($relFile) -> $filename"
        npx -y decktape reveal --size 1920x1080 $url $outFile
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "decktape failed for $key (exit $LASTEXITCODE)"
            $failed += $key
            continue
        }
        Copy-Item -Path $outFile -Destination (Join-Path $webOutPath $filename) -Force
    }
} finally {
    # Kill by port, not $server.Id -- that PID is cmd.exe (the wrapper
    # process, see the Start-Process comment above), and Stop-Process on a
    # parent doesn't kill its children on Windows (no process-group
    # semantics like Unix). The actual http-server/node process is a
    # grandchild and would otherwise leak past this script's exit.
    Write-Host "Stopping local server on port $Port..."
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
}

if ($failed.Count -gt 0) {
    Write-Error "Failed slides: $($failed -join ', ')"
    exit 1
}

Write-Host "Done. PDFs in $outPath (and $webOutPath for download links)"
