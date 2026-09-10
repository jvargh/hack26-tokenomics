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
Write-Host 'Log streaming may drop out on Windows; build status is confirmed below.'

# Record the newest run before building. `az acr build` does not return its run
# id, and "the most recent run" is not a safe proxy: if the build never starts
# (a bad path fails client-side) the most recent run is a *previous, successful*
# build, and trusting it would report success while shipping nothing.
$priorRunId = az acr task list-runs -r $Registry --top 1 --query "[0].runId" -o tsv 2>$null

# --file must be an absolute path. The Azure CLI resolves it against the current
# directory rather than the build context, so a relative name fails whenever the
# script is invoked from anywhere but the context directory.
$dockerfile = Join-Path $buildContext 'Dockerfile'

az acr build --registry $Registry `
    --image "${Repository}:${Tag}" `
    --image "${Repository}:latest" `
    --file $dockerfile $buildContext 2>&1 | Out-Host

# The CLI exit code is unreliable: it can die on a log-stream encoding error
# while the remote build carries on and succeeds. Confirm against the run record.
Write-Step 'Confirming build result'

$runId = $null
for ($i = 0; $i -lt 12; $i++) {
    $candidate = az acr task list-runs -r $Registry --top 1 --query "[0].runId" -o tsv 2>$null
    if ($candidate -and $candidate -ne $priorRunId) { $runId = $candidate; break }
    Start-Sleep -Seconds 5
}
if (-not $runId) {
    Fail 'No new ACR build run was created, so the build never started. Check the error above.'
}
Write-Host "Run : $runId (previous: $(if ($priorRunId) { $priorRunId } else { 'none' }))"

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

# Resolve by the tag just built, not by "most recent manifest": another push to
# the same repository would otherwise silently redirect this deployment.
$digest = az acr repository show -n $Registry --image "${Repository}:${Tag}" --query digest -o tsv 2>$null
if (-not $digest) { Fail "Could not resolve a digest for ${Repository}:${Tag}." }
Write-Host "Digest : $digest"

$imageRef = "$Registry.azurecr.io/${Repository}@$digest"

Write-Step 'Updating Container App'
Write-Host 'Only the image changes. Environment variables, identity and ingress are untouched.'

# Retried: this call reaches the control plane over a long-lived connection and
# can fail with a transient reset. Retrying is safe because setting the same
# image reference twice converges on the same state.
$updated = $false
for ($attempt = 1; $attempt -le 4; $attempt++) {
    az containerapp update -n $ContainerApp -g $ResourceGroup --image $imageRef -o none 2>&1 | Out-Host
    if ($LASTEXITCODE -eq 0) { $updated = $true; break }
    if ($attempt -lt 4) {
        Write-Host "Update attempt $attempt failed; retrying in 20s." -ForegroundColor Yellow
        Start-Sleep -Seconds 20
    }
}
if (-not $updated) { Fail 'Container App update failed after 4 attempts.' }

# Confirm the app really is on the image just built. The update call returning
# cleanly is not the same as the intended image being live.
$liveImage = az containerapp show -n $ContainerApp -g $ResourceGroup `
    --query "properties.template.containers[0].image" -o tsv 2>$null
if ($liveImage -ne $imageRef) {
    Fail "Container App reports image '$liveImage' but '$imageRef' was deployed."
}
Write-Host 'Image reference confirmed on the app.'

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
