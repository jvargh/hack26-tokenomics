# TokenOS — Start Both Backend & Frontend
$baseDir = $PSScriptRoot
if (Test-Path "$baseDir\services\tokenos-api") {
    $apiDir = "$baseDir\services\tokenos-api"
    $webDir = "$baseDir\apps\web"
} else {
    $apiDir = "$baseDir\tokenos\services\tokenos-api"
    $webDir = "$baseDir\tokenos\apps\web"
}

Write-Host "Starting TokenOS Backend API (Port 8000)..." -ForegroundColor Cyan
Start-Process -FilePath "$apiDir\.venv\Scripts\python.exe" `
  -ArgumentList "-m uvicorn tokenos_api.app:app --host 127.0.0.1 --port 8000" `
  -WorkingDirectory "$apiDir"

Write-Host "Starting TokenOS Web UI (Port 5173)..." -ForegroundColor Cyan
Start-Process -FilePath "cmd.exe" `
  -ArgumentList "/c npm run dev" `
  -WorkingDirectory "$webDir"

Write-Host "`nTokenOS started successfully!" -ForegroundColor Green
Write-Host "  Backend API: http://127.0.0.1:8000"
Write-Host "  Web UI:      http://localhost:5173`n"
