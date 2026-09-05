# TokenOS — Stop, Start & Restart Guide

This document contains complete instructions for stopping, starting, restarting, and configuring the TokenOS Web UI and Backend API using single commands or step-by-step terminals.

---

## 🛑 Overall STOP Approach (Fastest)

To stop all active TokenOS processes on ports 8000, 5173, 5174, and 5175:

### Option 1: Run the `stop.ps1` Script (Recommended)
```powershell
.\stop.ps1
```

### Option 2: Single-Line PowerShell Command
```powershell
Get-NetTCPConnection -LocalPort 8000,5173,5174,5175 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 0 } | ForEach-Object { Stop-Process -Id $_ -Force }
```

### Option 3: Stop All Node & Python Processes
```powershell
Stop-Process -Name node, python -Force -ErrorAction SilentlyContinue
```

---

## 🚀 Overall START Approach (Fastest)

To launch both the Backend API (`http://127.0.0.1:8000`) and Frontend Web UI (`http://localhost:5173`) simultaneously:

### Option 1: Run the `start.ps1` Script (Recommended)
```powershell
.\start.ps1
```

### Option 2: Single-Line PowerShell Command
```powershell
Start-Process -FilePath "tokenos\services\tokenos-api\.venv\Scripts\python.exe" -ArgumentList "-m uvicorn tokenos_api.app:app --host 127.0.0.1 --port 8000" -WorkingDirectory "tokenos\services\tokenos-api"; Start-Process -FilePath "cmd.exe" -ArgumentList "/c npm run dev" -WorkingDirectory "tokenos\apps\web"
```

---

## 🔄 Overall RESTART Approach

To stop everything and start fresh in a single command:

```powershell
.\stop.ps1; .\start.ps1
```

---

## 🚀 How to Start TokenOS

Run these commands in two separate terminal windows:

### Terminal 1: Start Backend API (Port 8000)
```powershell
Set-Location tokenos\services\tokenos-api
.\.venv\Scripts\python.exe -m uvicorn tokenos_api.app:app --host 127.0.0.1 --port 8000
```
- **API Health Check**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- **Interactive Swagger Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Terminal 2: Start Web UI (Port 5173)
```powershell
Set-Location tokenos\apps\web
npm run dev
```
- **Web Application**: [http://localhost:5173](http://localhost:5173)

---

## 🛑 How to Stop All Running TokenOS Processes

### Option 1: Stop by Port (Recommended)
Run this command in PowerShell to kill all processes listening on ports `8000`, `5173`, `5174`, or `5175`:

```powershell
Get-NetTCPConnection -LocalPort 8000,5173,5174,5175 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 0 } | ForEach-Object { Stop-Process -Id $_ -Force }
```

### Option 2: Stop All Node & Python Processes
To stop all Node (Vite) and Python (Uvicorn) processes system-wide:

**PowerShell:**
```powershell
Stop-Process -Name node, python -Force -ErrorAction SilentlyContinue
```

**Command Prompt (CMD):**
```cmd
taskkill /F /IM node.exe /IM python.exe
```

### Option 3: Manual Terminal Termination
In any open terminal window running `npm run dev` or `uvicorn`, press `Ctrl + C` and type `Y`.

---

## 🔄 Clean Restart Procedure

1. **Terminate background processes**: Run the Stop command above.
2. **Start Backend API**:
   ```powershell
   Set-Location tokenos\services\tokenos-api
   .\.venv\Scripts\python.exe -m uvicorn tokenos_api.app:app --host 127.0.0.1 --port 8000
   ```
3. **Start Web UI**:
   ```powershell
   Set-Location tokenos\apps\web
   npm run dev
   ```
4. **Open in Browser**: Navigate to [http://localhost:5173](http://localhost:5173).

---

## ⚡ Microsoft Foundry Configuration (Hybrid Mode)

### Option 1: UI Modal Configuration
1. Click the **⚙ Foundry Config** button in the header.
2. Enter your **Base URL** (e.g. `https://<resource>.openai.azure.com/openai/v1/`).
3. Set your **Efficient Deployment** (`tokenos-gpt41-nano`) and **Advanced Deployment** (`tokenos-gpt4o`).
4. Click **Test Connection** → **Save Configuration**.

### Option 2: Environment Variables
Set these variables before launching the API:

```powershell
$env:TOKENOS_MODEL_MODE = "foundry"
$env:TOKENOS_FOUNDRY_BASE_URL = "https://<resource>.openai.azure.com/openai/v1/"
$env:TOKENOS_FOUNDRY_EFFICIENT_DEPLOYMENT = "tokenos-gpt41-nano"
$env:TOKENOS_FOUNDRY_ADVANCED_DEPLOYMENT = "tokenos-gpt4o"
$env:TOKENOS_FOUNDRY_AUTH_MODE = "entra"

# Re-run the API
.\.venv\Scripts\python.exe -m uvicorn tokenos_api.app:app --host 127.0.0.1 --port 8000
```

---

## ❓ Troubleshooting Port Conflicts

If Vite opens on port `5175` instead of `5173` (e.g. `Local: http://localhost:5175/`), it means an earlier instance of `npm run dev` is still running in the background.

To return to port `5173`:
1. Run Option 1 or Option 2 stop command above.
2. Re-run `npm run dev` in `tokenos\apps\web`.
