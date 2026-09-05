# Starts the TokenOS API with the hybrid Foundry routes enabled.
#
# Auth is Microsoft Entra ID, not an API key. The Azure OpenAI resource has local
# auth disabled, so the signed-in principal must hold "Cognitive Services OpenAI
# User" on the account. Sign in with `az login` before running this.
#
#   .\start-foundry.ps1

$env:TOKENOS_MODEL_MODE = "foundry"
$env:TOKENOS_FOUNDRY_BASE_URL = "https://aoai-tokenos-wxyc7mhwpamee.openai.azure.com/openai/v1/"
$env:TOKENOS_FOUNDRY_EFFICIENT_DEPLOYMENT = "tokenos-gpt41-nano"
$env:TOKENOS_FOUNDRY_ADVANCED_DEPLOYMENT = "tokenos-gpt4o"
$env:TOKENOS_FOUNDRY_AUTH_MODE = "entra"
$env:TOKENOS_FOUNDRY_TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"

Write-Host "Efficient route -> $env:TOKENOS_FOUNDRY_EFFICIENT_DEPLOYMENT"
Write-Host "Advanced route  -> $env:TOKENOS_FOUNDRY_ADVANCED_DEPLOYMENT"
Write-Host "Auth            -> Entra ID (no key in this process)"

Push-Location $PSScriptRoot
try {
    python -m uvicorn tokenos_api.main:app --host 127.0.0.1 --port 8000
} finally {
    Pop-Location
}
