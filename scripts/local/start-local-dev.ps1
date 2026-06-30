param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..\..")
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$BackendPython = Join-Path $BackendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $BackendPython)) {
    throw "Backend virtual environment missing. Run: cd backend; python -m venv .venv; .\.venv\Scripts\python -m pip install -r requirements.txt"
}

if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    throw "Frontend dependencies missing. Run: cd frontend; npm install"
}

$backendCommand = "cd '$BackendDir'; .\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port $ApiPort"
$frontendCommand = "cd '$FrontendDir'; npm run dev -- --host 127.0.0.1 --port $WebPort"

Start-Process powershell -ArgumentList @("-NoExit", "-Command", $backendCommand) -WorkingDirectory $BackendDir
Start-Process powershell -ArgumentList @("-NoExit", "-Command", $frontendCommand) -WorkingDirectory $FrontendDir

Write-Host "ROCmPorter local dev started."
Write-Host "Backend:  http://127.0.0.1:$ApiPort"
Write-Host "Frontend: http://127.0.0.1:$WebPort"
Write-Host "Ollama:   http://127.0.0.1:11434"
