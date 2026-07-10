param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5178,
    [string]$Model = "qwen2.5-coder:latest",
    [switch]$SkipWarm,
    [switch]$Visible
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..\..")
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$BackendPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$StateDir = Join-Path $Root "work\local-dev"
$StateFile = Join-Path $StateDir "state.json"
$BackendLog = Join-Path $StateDir "backend.log"
$FrontendLog = Join-Path $StateDir "frontend.log"

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

function Test-HttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSec = 3
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Wait-HttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSec = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-HttpOk -Url $Url -TimeoutSec 2) {
            return $true
        }
        Start-Sleep -Milliseconds 700
    }

    return $false
}

function Start-DevProcess {
    param(
        [string]$Name,
        [string]$Command,
        [string]$WorkingDirectory
    )

    $arguments = if ($Visible) {
        @("-NoProfile", "-NoExit", "-Command", $Command)
    } else {
        @("-NoProfile", "-Command", $Command)
    }

    $windowStyle = if ($Visible) { "Normal" } else { "Hidden" }
    $process = Start-Process powershell -ArgumentList $arguments -WorkingDirectory $WorkingDirectory -WindowStyle $windowStyle -PassThru
    Write-Host "Starting $Name`:        PID $($process.Id)"
    return $process
}

if (-not (Test-Path $BackendPython)) {
    Write-Host "Backend virtual environment missing - creating it now (one-time setup)..."
    Push-Location $BackendDir
    try {
        python -m venv .venv
        if (-not (Test-Path $BackendPython)) {
            throw "Could not create backend\.venv. Install Python 3.10+ and retry."
        }
        & $BackendPython -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) {
            throw "Backend dependency install failed. Run manually: cd backend; .\.venv\Scripts\python -m pip install -r requirements.txt"
        }
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Host "Frontend dependencies missing - running npm install (one-time setup)..."
    Push-Location $FrontendDir
    try {
        npm install
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend dependency install failed. Run manually: cd frontend; npm install"
        }
    } finally {
        Pop-Location
    }
}

$backendUrl = "http://127.0.0.1:$ApiPort"
$frontendUrl = "http://127.0.0.1:$WebPort"
$ollamaUrl = "http://127.0.0.1:11434"
$backendProcess = $null
$frontendProcess = $null

if (Test-HttpOk -Url "$backendUrl/api/health") {
    Write-Host "Backend already running:  $backendUrl"
} else {
    $backendCommand = "cd '$BackendDir'; .\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port $ApiPort *> '$BackendLog'"
    $backendProcess = Start-DevProcess -Name "backend" -Command $backendCommand -WorkingDirectory $BackendDir
}

if (Test-HttpOk -Url $frontendUrl) {
    Write-Host "Frontend already running: $frontendUrl"
} else {
    $frontendCommand = "`$env:VITE_API_PROXY_TARGET='$backendUrl'; cd '$FrontendDir'; npm run dev -- --host 127.0.0.1 --port $WebPort *> '$FrontendLog'"
    $frontendProcess = Start-DevProcess -Name "frontend" -Command $frontendCommand -WorkingDirectory $FrontendDir
}

$backendReady = Wait-HttpOk -Url "$backendUrl/api/health" -TimeoutSec 35
if (-not $backendReady) {
    throw "Backend did not become ready at $backendUrl. Check the backend log for errors: $BackendLog"
}

if (-not (Test-HttpOk -Url "$ollamaUrl/api/tags")) {
    Write-Warning "Ollama is not reachable at $ollamaUrl. Start Ollama before generating patches."
} elseif (-not $SkipWarm) {
    Write-Host "Warming Ollama model:   $Model"
    try {
        $body = @{ model = $Model } | ConvertTo-Json -Compress
        $status = Invoke-RestMethod -Uri "$backendUrl/api/ollama/warm" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 120
        Write-Host "Ollama status:          $($status.summary)"
    } catch {
        Write-Warning "Could not warm $Model. The app can still run, but first patch generation may be slow. $($_.Exception.Message)"
    }
}

$frontendReady = Wait-HttpOk -Url $frontendUrl -TimeoutSec 35
if (-not $frontendReady) {
    throw "Frontend did not become ready at $frontendUrl. Check the frontend log for errors: $FrontendLog"
}

$state = [ordered]@{
    startedAt = (Get-Date).ToString("o")
    root = "$Root"
    backend = [ordered]@{
        url = $backendUrl
        port = $ApiPort
        pid = if ($backendProcess) { $backendProcess.Id } else { $null }
        log = $BackendLog
    }
    frontend = [ordered]@{
        url = $frontendUrl
        port = $WebPort
        pid = if ($frontendProcess) { $frontendProcess.Id } else { $null }
        log = $FrontendLog
    }
    ollama = [ordered]@{
        url = $ollamaUrl
        model = $Model
    }
}

$state | ConvertTo-Json -Depth 5 | Set-Content -Path $StateFile -Encoding UTF8

Write-Host "ROCmPorter local dev started."
Write-Host "Backend:  $backendUrl"
Write-Host "Frontend: $frontendUrl"
Write-Host "Ollama:   $ollamaUrl"
Write-Host "Logs:     $StateDir"
Write-Host "Status:   .\scripts\local\status-local-dev.ps1"
Write-Host "Stop:     .\scripts\local\stop-local-dev.ps1"
