<#
.SYNOPSIS
    Builds and deploys the simulated judge demonstration to Azure Container Apps.

.DESCRIPTION
    Replaces the image on the existing Container App with a build that answers
    model routes from the authored simulator. The application's real-model
    behaviour is unaffected: it is selected by TOKENOS_MODEL_MODE, and local
    runs are untouched.

    Deliberate safety properties, several learned the hard way in
    infra/redeploy.ps1:

    - `az acr build --file` is resolved against the CURRENT directory, not the
      build context, so an absolute path is passed.
    - The Azure CLI log stream dies on Windows with a UnicodeEncodeError when
      the web build prints a character it cannot encode in cp1252. The CLI exit
      code is therefore unreliable. This records the newest ACR run id BEFORE
      building and requires a genuinely NEW run id afterwards: without that
      check a build that never started would silently "succeed" against a
      previous run and deploy nothing.
    - The image is deployed by digest, not tag. A tag can later be moved; a
      digest records exactly what shipped.
    - Every long-running Azure call has a timeout so a stalled operation cannot
      hang indefinitely.

.PARAMETER Yes
    Skip the interactive confirmation. Intended for re-runs after the cost and
    target have already been reviewed once.

.EXAMPLE
    .\deploy.ps1
#>

[CmdletBinding()]
param(
    [string]$ResourceGroup = 'azrgda6pvyru4svsw',
    [string]$ContainerApp  = 'tokenos-hack26',
    [string]$Registry      = 'azacrda6pvyru4svsw',
    [string]$Repository    = 'tokenos/tokenos-tokenos-hack26',
    [string]$Tag,
    [switch]$Yes,
    [switch]$SkipVerify,
    [int]$BuildTimeoutMinutes  = 25,
    [int]$DeployTimeoutMinutes = 15
)

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'

$repoRoot = Split-Path -Parent $PSScriptRoot
$acaRoot  = $PSScriptRoot

function Write-Step { param([string]$Text) Write-Host "`n=== $Text ===" -ForegroundColor Cyan }
function Fail { param([string]$Text) Write-Host "ERROR: $Text" -ForegroundColor Red; exit 1 }

# ------------------------------------------------------------- preflight

Write-Step 'Preflight'

if (-not (Get-Command az -ErrorAction SilentlyContinue)) { Fail 'Azure CLI (az) is not on PATH.' }

$account = az account show --query "{name:name, id:id}" -o json 2>$null | ConvertFrom-Json
if (-not $account) { Fail 'Not signed in to Azure. Run: az login' }

if (-not $Tag) {
    $Tag = "sim-$((git -C $repoRoot rev-parse --short HEAD).Trim())"
}

$existing = az containerapp show -n $ContainerApp -g $ResourceGroup `
    --query "{fqdn:properties.configuration.ingress.fqdn, image:properties.template.containers[0].image}" `
    -o json 2>$null | ConvertFrom-Json
if (-not $existing) { Fail "Container App '$ContainerApp' not found in '$ResourceGroup'." }

# ------------------------------------------------------------- disclosure

Write-Step 'Deployment target'

Write-Host "Subscription    : $($account.name)"
Write-Host "Subscription ID : $($account.id)"
Write-Host "Resource group  : $ResourceGroup"
Write-Host "Region          : $(az group show -n $ResourceGroup --query location -o tsv 2>$null)"
Write-Host "Container App   : $ContainerApp"
Write-Host "Registry        : $Registry.azurecr.io"
Write-Host "Image tag       : $Tag"
Write-Host "Public URL      : https://$($existing.fqdn)"
Write-Host "Current image   : $($existing.image)"
Write-Host ""
Write-Host "Model mode      : simulated (no provider calls, no model spend)" -ForegroundColor Green

Write-Step 'Estimated hosting cost'
Write-Host 'Retail eastus rates. The app already runs one replica continuously,'
Write-Host 'so this deployment does not change the running cost.'
Write-Host '  vCPU 0.5 active            ~$31.54 / month   (already incurred)'
Write-Host '  Memory 1 GiB active        ~$7.88  / month   (already incurred)'
Write-Host '  Environment management     ~$73.00 / month   (already incurred)'
Write-Host '  New billable resources      none'
Write-Host '  ------------------------------------------------'
Write-Host '  Marginal cost of this deployment: $0.00 / month' -ForegroundColor Green
Write-Host ''
Write-Host 'Model inference cost: $0.00. The image contains no provider SDK.' -ForegroundColor Green

if (-not $Yes) {
    Write-Host ''
    $answer = Read-Host 'Proceed with build and deployment to the resources above? (yes/no)'
    if ($answer -ne 'yes') { Write-Host 'Cancelled. Nothing was changed.'; exit 0 }
}

# ----------------------------------------------------------------- build

Write-Step 'Building image in ACR'

# The build context is staged rather than uploaded from the repository root.
#
# `az acr build` reads .dockerignore from the CONTEXT ROOT, not from beside the
# Dockerfile, so aca/.dockerignore is never consulted when the context is the
# repository. The first attempt therefore uploaded 223 MiB including
# node_modules, and the stale non-executable tsc inside it shadowed the freshly
# installed one, failing the web build with "tsc: Permission denied".
#
# Copying only the allowlisted paths into a temporary directory is stricter than
# any ignore file: anything not copied cannot reach the image even by accident,
# and no .dockerignore has to be added at the repository root where it would
# also affect the production build.
$stage = Join-Path ([System.IO.Path]::GetTempPath()) "tokenos-aca-$(Get-Random)"
New-Item -ItemType Directory -Path $stage -Force | Out-Null

try {
    $webSource = Join-Path $repoRoot 'tokenos\apps\web'
    $apiSource = Join-Path $repoRoot 'tokenos\services\tokenos-api'
    $webStage  = Join-Path $stage 'tokenos\apps\web'
    $apiStage  = Join-Path $stage 'tokenos\services\tokenos-api'
    New-Item -ItemType Directory -Path $webStage, $apiStage -Force | Out-Null

    # Excluded for correctness as well as size: node_modules breaks the build,
    # a .venv would bloat the upload, tests are not shipped, and a stray
    # SQLite file or .env would leak local history or configuration.
    $excluded = @('node_modules', '.venv', 'dist', 'tests', '.pytest_cache',
                  '__pycache__', 'static', '.git')

    function Copy-Allowed {
        param([string]$Source, [string]$Destination)
        Get-ChildItem -LiteralPath $Source -Force | ForEach-Object {
            if ($_.PSIsContainer) {
                if ($excluded -contains $_.Name) { return }
                $child = Join-Path $Destination $_.Name
                New-Item -ItemType Directory -Path $child -Force | Out-Null
                Copy-Allowed -Source $_.FullName -Destination $child
            } else {
                if ($_.Name -match '\.(sqlite3|pyc|log|bak)$' -or $_.Name -like '.env*') { return }
                Copy-Item -LiteralPath $_.FullName -Destination $Destination -Force
            }
        }
    }

    Copy-Allowed -Source $webSource -Destination $webStage
    Copy-Allowed -Source $apiSource -Destination $apiStage

    $stagedMb = [math]::Round(((Get-ChildItem $stage -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
    Write-Host "Staged build context: $stagedMb MB"

    # Guard rather than trust: a leaked secret or local history would be shipped
    # in a publicly reachable image.
    $leaked = Get-ChildItem $stage -Recurse -File -Force |
        Where-Object { $_.Name -like '.env*' -or $_.Extension -eq '.sqlite3' -or $_.FullName -match 'node_modules|\.venv' }
    if ($leaked) {
        Fail "Staged context contains files that must not ship: $($leaked[0].FullName)"
    }

    # See the note in the header: "the most recent run" is not a safe proxy for
    # "my run" when a build fails before it is queued.
    $priorRunId = az acr task list-runs -r $Registry --top 1 --query "[0].runId" -o tsv 2>$null
    $dockerfile = Join-Path $acaRoot 'Dockerfile'

    $build = Start-Job -ScriptBlock {
        param($registry, $repository, $tag, $dockerfile, $context)
        $env:PYTHONIOENCODING = 'utf-8'
        az acr build --registry $registry `
            --image "${repository}:${tag}" `
            --file $dockerfile $context 2>&1
    } -ArgumentList $Registry, $Repository, $Tag, $dockerfile, $stage

    if (-not (Wait-Job $build -Timeout ($BuildTimeoutMinutes * 60))) {
        Stop-Job $build; Remove-Job $build -Force
        Fail "Build did not finish within $BuildTimeoutMinutes minutes."
    }
    Receive-Job $build | Out-Host
    Remove-Job $build -Force
}
finally {
    Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Step 'Confirming build result'

$runId = $null
for ($i = 0; $i -lt 12; $i++) {
    $candidate = az acr task list-runs -r $Registry --top 1 --query "[0].runId" -o tsv 2>$null
    if ($candidate -and $candidate -ne $priorRunId) { $runId = $candidate; break }
    Start-Sleep -Seconds 5
}
if (-not $runId) { Fail 'No new ACR run was created, so the build never started. Check the error above.' }

$status = $null
for ($i = 0; $i -lt ($BuildTimeoutMinutes * 4); $i++) {
    $status = az acr task show-run -r $Registry --run-id $runId --query status -o tsv 2>$null
    if ($status -and $status -notmatch '^(Running|Queued|Started)$') { break }
    Start-Sleep -Seconds 15
}
if ($status -ne 'Succeeded') {
    Fail "Build status: $status. Logs: az acr task logs -r $Registry --run-id $runId"
}
Write-Host "Build succeeded (run $runId)." -ForegroundColor Green

# ---------------------------------------------------------------- deploy

Write-Step 'Resolving image digest'

$digest = az acr repository show -n $Registry --image "${Repository}:${Tag}" --query digest -o tsv 2>$null
if (-not $digest) { Fail "Could not resolve a digest for ${Repository}:${Tag}." }
$imageRef = "$Registry.azurecr.io/${Repository}@$digest"
Write-Host "Digest : $digest"

Write-Step 'Updating Container App'

# TOKENOS_MODEL_MODE is set explicitly rather than relying on the image default,
# so the deployed configuration states the mode plainly. The Foundry variables
# are removed: the judge build must not carry a provider endpoint at all.
$deploy = Start-Job -ScriptBlock {
    param($app, $rg, $image)
    $env:PYTHONIOENCODING = 'utf-8'
    for ($attempt = 1; $attempt -le 4; $attempt++) {
        az containerapp update -n $app -g $rg --image $image `
            --set-env-vars `
                TOKENOS_MODEL_MODE=simulated `
                TOKENOS_STORAGE_ROOT=/data/tokenos `
                TOKENOS_WEB_DIST_ROOT=/app/services/tokenos-api/static `
            --remove-env-vars `
                TOKENOS_FOUNDRY_BASE_URL `
                TOKENOS_FOUNDRY_EFFICIENT_DEPLOYMENT `
                TOKENOS_FOUNDRY_ADVANCED_DEPLOYMENT `
                TOKENOS_FOUNDRY_AUTH_MODE `
            -o none 2>&1
        if ($LASTEXITCODE -eq 0) { return 'ok' }
        Start-Sleep -Seconds 20
    }
    return 'failed'
} -ArgumentList $ContainerApp, $ResourceGroup, $imageRef

if (-not (Wait-Job $deploy -Timeout ($DeployTimeoutMinutes * 60))) {
    Stop-Job $deploy; Remove-Job $deploy -Force
    Fail "Deployment did not finish within $DeployTimeoutMinutes minutes."
}
$outcome = Receive-Job $deploy | Select-Object -Last 1
Remove-Job $deploy -Force
if ($outcome -ne 'ok') { Fail 'Container App update failed after 4 attempts.' }

$liveImage = az containerapp show -n $ContainerApp -g $ResourceGroup `
    --query "properties.template.containers[0].image" -o tsv 2>$null
if ($liveImage -ne $imageRef) { Fail "App reports '$liveImage' but '$imageRef' was deployed." }
Write-Host 'Image reference confirmed on the app.' -ForegroundColor Green

Write-Step 'Waiting for the new revision'

$revision = az containerapp show -n $ContainerApp -g $ResourceGroup --query "properties.latestRevisionName" -o tsv 2>$null
$state = $null
for ($i = 0; $i -lt 40; $i++) {
    $state = az containerapp revision show -n $ContainerApp -g $ResourceGroup --revision $revision `
        --query "{running:properties.runningState, health:properties.healthState}" -o json 2>$null | ConvertFrom-Json
    if ($state.running -eq 'Running') { break }
    if ($state.running -match 'Failed|Degraded') {
        Fail "Revision $revision entered '$($state.running)'. Logs: az containerapp logs show -n $ContainerApp -g $ResourceGroup --revision $revision"
    }
    Start-Sleep -Seconds 10
}
if ($state.running -ne 'Running') { Fail "Revision $revision did not reach Running." }
Write-Host "Revision $revision running (health: $($state.health))." -ForegroundColor Green

# ---------------------------------------------------------------- verify

$baseUrl = "https://$($existing.fqdn)"

Write-Step 'Verifying simulated mode is live'

$health = $null
for ($i = 0; $i -lt 20; $i++) {
    try { $health = Invoke-RestMethod "$baseUrl/health" -TimeoutSec 30; break } catch { Start-Sleep -Seconds 10 }
}
if (-not $health) { Fail "Health endpoint did not respond at $baseUrl/health" }

Write-Host "modelMode: $($health.modelMode)"
if ($health.modelMode -ne 'simulated') {
    Fail "Deployed app reports modelMode '$($health.modelMode)'. It must be 'simulated'."
}
if ($health.foundryAvailable) {
    Fail 'Deployed app reports a reachable Foundry deployment. It must not.'
}
Write-Host 'Simulated mode confirmed; no provider configured.' -ForegroundColor Green

if (-not $SkipVerify) {
    Write-Step 'Judge journey verification'
    $verify = Join-Path $acaRoot 'verify_deployed.py'
    if (Test-Path $verify) {
        python $verify $baseUrl
        if ($LASTEXITCODE -ne 0) { Fail 'Judge journey verification failed. The deployment is live but not verified.' }
    } else {
        Write-Host "Verification script not found at $verify; skipping." -ForegroundColor Yellow
    }
}

Write-Host "`nDeployed $Tag to $baseUrl" -ForegroundColor Green
Write-Host "Image    : $imageRef"
Write-Host "Revision : $revision"
