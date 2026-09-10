<#
.SYNOPSIS
    Rebuilds the TokenOS container image and points the existing Container App at it.

.DESCRIPTION
    A redeploy-only path. It does NOT provision infrastructure and does NOT touch
    environment variables, managed identity, ingress or CORS: those already exist
    on the running app, and re-running `azd up` against live infrastructure to
    ship a code change is a much larger action than the change warrants. Use
    `azd up` (see the README) for first-time provisioning or when the Bicep
    itself changes.

    The image is built in Azure Container Registry rather than locally, so no
    Docker daemon is needed and the build host has the network access that the
    local Docker build lacks (see tokenos/vendor-wheels/README.md).

    The Container App is updated by image digest, not tag. A tag can be moved to
    point at different content; a digest cannot, so the revision records exactly
    what was deployed.

.PARAMETER ResourceGroup
    Resource group holding the Container App and registry.

.PARAMETER ContainerApp
    Name of the existing Container App to update.

.PARAMETER Registry
    Azure Container Registry name (not the login server).

.PARAMETER Repository
    Image repository within the registry.

.PARAMETER Tag
    Image tag. Defaults to the current git commit SHA, so a deployed image can
    always be traced back to source.

.PARAMETER AllowDirty
    Permit deploying with uncommitted changes. Off by default: the default tag is
    a commit SHA, and tagging modified content with a clean commit's SHA makes the
    image a lie about what it contains.

.PARAMETER SkipSmokeTest
    Skip the post-deploy browser verification.

.EXAMPLE
    .\redeploy.ps1
    Build from the current commit and roll it out.

.EXAMPLE
    .\redeploy.ps1 -Tag hotfix-1 -AllowDirty
    Build uncommitted work under an explicit tag.
#>

[CmdletBinding()]
param(
    [string]$ResourceGroup = 'azrgda6pvyru4svsw',
    [string]$ContainerApp  = 'tokenos-hack26',
    [string]$Registry      = 'azacrda6pvyru4svsw',
    [string]$Repository    = 'tokenos/tokenos-tokenos-hack26',
    [string]$Tag,
    [switch]$AllowDirty,
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = 'Stop'

# The Azure CLI streams build logs through a cp1252 console writer on Windows.
# The web build prints U+2713, which that writer cannot encode, and the CLI dies
# mid-stream with a UnicodeEncodeError even though the remote build is fine.
$env:PYTHONIOENCODING = 'utf-8'

$repoRoot    = Split-Path -Parent $PSScriptRoot
$buildContext = Join-Path $repoRoot 'tokenos'

function Write-Step { param([string]$Text) Write-Host "`n=== $Text ===" -ForegroundColor Cyan }
function Fail { param([string]$Text) Write-Host "ERROR: $Text" -ForegroundColor Red; exit 1 }

# --------------------------------------------------------------- preflight

Write-Step 'Preflight'

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    Fail 'Azure CLI (az) is not on PATH. See the README for installation.'
}

$account = az account show --query "{name:name, id:id}" -o json 2>$null | ConvertFrom-Json
if (-not $account) { Fail 'Not signed in to Azure. Run: az login' }
Write-Host "Subscription : $($account.name)"

if (-not (Test-Path (Join-Path $buildContext 'Dockerfile'))) {
    Fail "No Dockerfile at $buildContext. Run this script from the repository."
}

# The wheels are installed with --no-index, so an empty folder fails the build
# well into it rather than immediately. Catch it here instead.
$wheels = Get-ChildItem (Join-Path $buildContext 'vendor-wheels') -Filter *.whl -ErrorAction SilentlyContinue
if (-not $wheels) {
    Fail 'tokenos/vendor-wheels contains no .whl files. See tokenos/vendor-wheels/README.md to regenerate them.'
}
Write-Host "Vendored wheels : $($wheels.Count)"

$dirty = git -C $repoRoot status --porcelain
if ($dirty -and -not $AllowDirty) {
    Write-Host 'Uncommitted changes:' -ForegroundColor Yellow
    $dirty | ForEach-Object { Write-Host "  $_" }
    Fail 'Working tree is dirty. Commit first, or pass -AllowDirty with an explicit -Tag.'
}

if (-not $Tag) {
    $Tag = (git -C $repoRoot rev-parse --short HEAD).Trim()
    if (-not $Tag) { Fail 'Could not resolve a git commit for the image tag. Pass -Tag explicitly.' }
}
Write-Host "Image tag : $Tag"

# Fail before spending several minutes on a build that has nowhere to go.
$existing = az containerapp show -n $ContainerApp -g $ResourceGroup `
    --query "{fqdn:properties.configuration.ingress.fqdn, image:properties.template.containers[0].image}" `
    -o json 2>$null | ConvertFrom-Json
if (-not $existing) {
    Fail "Container App '$ContainerApp' not found in '$ResourceGroup'. For first-time provisioning use 'azd up' (see README)."
}
Write-Host "Target app : https://$($existing.fqdn)"
Write-Host "Current image : $($existing.image)"

# ------------------------------------------------------------------- build

Write-Step 'Building image in ACR'
Write-Host 'Log streaming may drop out on Windows; build status is polled below.'

az acr build --registry $Registry `
    --image "${Repository}:${Tag}" `
    --image "${Repository}:latest" `
    --file Dockerfile $buildContext 2>&1 | Out-Host

# Exit code is unreliable here: the CLI can die on a log-stream encoding error
# while the remote build carries on and succeeds. Trust the run record instead.
Write-Step 'Confirming build result'

$runId = az acr task list-runs -r $Registry --top 1 --query "[0].runId" -o tsv 2>$null
if (-not $runId) { Fail 'Could not identify the ACR build run.' }
Write-Host "Run : $runId"

$status = $null
for ($i = 0; $i -lt 80; $i++) {
    $status = az acr task show-run -r $Registry --run-id $runId --query status -o tsv 2>$null
    if ($status -and $status -notmatch '^(Running|Queued|Started)$') { break }
    Start-Sleep -Seconds 15
}
if ($status -ne 'Succeeded') {
    Fail "Build did not succeed (status: $status). Logs: az acr task logs -r $Registry --run-id $runId"
}
Write-Host 'Build succeeded.' -ForegroundColor Green

# ------------------------------------------------------------------ deploy

Write-Step 'Resolving image digest'

$digest = az acr manifest list-metadata -r $Registry -n $Repository `
    --orderby time_desc --top 1 --query "[0].digest" -o tsv 2>$null
if (-not $digest) { Fail 'Could not resolve the image digest.' }
Write-Host "Digest : $digest"

$imageRef = "$Registry.azurecr.io/${Repository}@$digest"

Write-Step 'Updating Container App'
Write-Host 'Only the image changes. Environment variables, identity and ingress are untouched.'

az containerapp update -n $ContainerApp -g $ResourceGroup --image $imageRef -o none 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { Fail 'Container App update failed.' }

Write-Step 'Waiting for the new revision'

$revision = az containerapp show -n $ContainerApp -g $ResourceGroup `
    --query "properties.latestRevisionName" -o tsv 2>$null
Write-Host "Revision : $revision"

$state = $null
for ($i = 0; $i -lt 40; $i++) {
    $state = az containerapp revision show -n $ContainerApp -g $ResourceGroup --revision $revision `
        --query "{running:properties.runningState, health:properties.healthState}" -o json 2>$null | ConvertFrom-Json
    if ($state.running -eq 'Running') { break }
    if ($state.running -match 'Failed|Degraded') {
        Fail "Revision $revision entered state '$($state.running)'. Logs: az containerapp logs show -n $ContainerApp -g $ResourceGroup --revision $revision"
    }
    Start-Sleep -Seconds 10
}
if ($state.running -ne 'Running') {
    Fail "Revision $revision did not reach Running (last state: $($state.running))."
}
Write-Host "Revision running (health: $($state.health))." -ForegroundColor Green

# ------------------------------------------------------------------ verify

$baseUrl = "https://$($existing.fqdn)"

Write-Step 'Verifying health endpoint'
$health = $null
for ($i = 0; $i -lt 20; $i++) {
    try { $health = Invoke-RestMethod "$baseUrl/health" -TimeoutSec 30; break }
    catch { Start-Sleep -Seconds 10 }
}
if (-not $health) { Fail "Health endpoint did not respond at $baseUrl/health" }
Write-Host "status=$($health.status) modelMode=$($health.modelMode) foundryAvailable=$($health.foundryAvailable)"

if (-not $SkipSmokeTest) {
    Write-Step 'Post-deploy smoke test'
    $smoke = Join-Path $repoRoot 'tokenos\services\tokenos-api\tests\browser\smoke_deployed.py'
    if (Test-Path $smoke) {
        python $smoke $baseUrl
        if ($LASTEXITCODE -ne 0) { Fail 'Smoke test failed. The deployment is live but not verified.' }
    } else {
        Write-Host "Smoke test not found at $smoke; skipping." -ForegroundColor Yellow
    }
}

Write-Host "`nDeployed $Tag to $baseUrl" -ForegroundColor Green
Write-Host "Image: $imageRef"
