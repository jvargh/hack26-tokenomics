<#
.SYNOPSIS
    Restores the Container App to the pre-demonstration real-model image.

.DESCRIPTION
    Undoes deploy.ps1. The digest below is the image the app was running before
    the judge demonstration was deployed, captured so a rollback never depends
    on a tag that may since have moved.

    This restores the IMAGE and the model mode. It does not restore the
    `Cognitive Services OpenAI User` role assignment removed during the
    demonstration; that command is printed at the end so the change is explicit
    rather than silent.

.EXAMPLE
    .\rollback.ps1
#>

[CmdletBinding()]
param(
    [string]$ResourceGroup = 'azrgda6pvyru4svsw',
    [string]$ContainerApp  = 'tokenos-hack26',
    [string]$Digest        = 'sha256:e8742dfed563da9017d805604f62a0523c7004b6d49d9620252020ed3e82eb51',
    [string]$Registry      = 'azacrda6pvyru4svsw',
    [string]$Repository    = 'tokenos/tokenos-tokenos-hack26',
    [switch]$Yes
)

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'

$imageRef = "$Registry.azurecr.io/$Repository@$Digest"

Write-Host "Rolling $ContainerApp back to:" -ForegroundColor Cyan
Write-Host "  $imageRef"
Write-Host ''
Write-Host 'This restores real-model behaviour. Model calls will cost money again.' -ForegroundColor Yellow

if (-not $Yes) {
    $answer = Read-Host 'Proceed? (yes/no)'
    if ($answer -ne 'yes') { Write-Host 'Cancelled.'; exit 0 }
}

az containerapp update -n $ContainerApp -g $ResourceGroup --image $imageRef `
    --set-env-vars TOKENOS_MODEL_MODE=foundry -o none
if ($LASTEXITCODE -ne 0) { Write-Host 'Rollback failed.' -ForegroundColor Red; exit 1 }

Write-Host 'Image restored.' -ForegroundColor Green
Write-Host ''
Write-Host 'The Foundry endpoint variables and the model-inference role were removed' -ForegroundColor Yellow
Write-Host 'for the demonstration. Restore them before expecting real model routes:'
Write-Host ''
Write-Host '  az containerapp update -n tokenos-hack26 -g azrgda6pvyru4svsw --set-env-vars \'
Write-Host '    TOKENOS_FOUNDRY_BASE_URL=https://aoai-tokenos-wxyc7mhwpamee.openai.azure.com/openai/v1/ \'
Write-Host '    TOKENOS_FOUNDRY_EFFICIENT_DEPLOYMENT=tokenos-gpt41-nano \'
Write-Host '    TOKENOS_FOUNDRY_ADVANCED_DEPLOYMENT=tokenos-gpt4o \'
Write-Host '    TOKENOS_FOUNDRY_AUTH_MODE=entra'
Write-Host ''
Write-Host '  az role assignment create --assignee 2cdaa814-86d1-4951-8e81-d1e8a42ff145 \'
Write-Host '    --role "Cognitive Services OpenAI User" \'
Write-Host '    --scope /subscriptions/463a82d4-1896-4332-aeeb-618ee5a5aa93/resourceGroups/rg-tokenos/providers/Microsoft.CognitiveServices/accounts/aoai-tokenos-wxyc7mhwpamee'
