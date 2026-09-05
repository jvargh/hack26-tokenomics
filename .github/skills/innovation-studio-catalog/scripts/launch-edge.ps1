param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^https://innovation-studio\.microsoft\.com/')]
    [string]$Url,

    [ValidateRange(1024, 65535)]
    [int]$Port = 9222,

    [string]$ProfileDirectory = "$env:USERPROFILE\.copilot\innovation-studio-edge-profile"
)

$ErrorActionPreference = "Stop"
$endpoint = "http://127.0.0.1:$Port"

try {
    $version = Invoke-RestMethod -Uri "$endpoint/json/version" -TimeoutSec 2
    if ($version.Browser) {
        Write-Output "Edge debugging session is already available."
        Write-Output "CDP_ENDPOINT=$endpoint"
        Write-Output "PROFILE=$ProfileDirectory"
        exit 0
    }
}
catch {
    # No existing debugging session is listening on this dedicated port.
}

$edgeCandidates = @(
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe"
)
$edge = $edgeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $edge) {
    throw "Microsoft Edge was not found in a standard installation location."
}

New-Item -ItemType Directory -Force -Path $ProfileDirectory | Out-Null
$process = Start-Process -FilePath $edge -ArgumentList @(
    "--remote-debugging-port=$Port",
    "--user-data-dir=$ProfileDirectory",
    "--no-first-run",
    "--new-window",
    $Url
) -PassThru

Start-Sleep -Seconds 3
if ($process.HasExited) {
    throw "Microsoft Edge exited before opening the Innovation Studio page."
}

Write-Output "EDGE_PID=$($process.Id)"
Write-Output "CDP_ENDPOINT=$endpoint"
Write-Output "PROFILE=$ProfileDirectory"
Write-Output "Complete sign-in in the external Edge window, then run scripts\extract.js."
