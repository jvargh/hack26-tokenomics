# TokenOS — Stop Both Backend & Frontend
Write-Host "Stopping TokenOS processes on ports 8000, 5173, 5174, 5175..." -ForegroundColor Yellow

$pids = Get-NetTCPConnection -LocalPort 8000,5173,5174,5175 -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  Where-Object { $_ -gt 0 }

if ($pids) {
    foreach ($pidToKill in $pids) {
        try {
            Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped process ID $pidToKill" -ForegroundColor Green
        } catch {
            /* ignore */
        }
    }
    Write-Host "All TokenOS processes stopped successfully." -ForegroundColor Green
} else {
    Write-Host "No active TokenOS processes found on ports 8000, 5173, 5174, 5175." -ForegroundColor Gray
}
