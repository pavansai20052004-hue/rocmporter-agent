param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5178
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..\..")
$StateFile = Join-Path $Root "work\local-dev\state.json"

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

function Write-Status {
    param(
        [string]$Name,
        [string]$Url,
        [bool]$Ready
    )

    $state = if ($Ready) { "OK" } else { "DOWN" }
    Write-Host ("[{0}] {1}: {2}" -f $state, $Name, $Url)
}

$state = $null
if (Test-Path $StateFile) {
    $state = Get-Content -Raw $StateFile | ConvertFrom-Json
    $ApiPort = [int]$state.backend.port
    $WebPort = [int]$state.frontend.port
}

$backendUrl = "http://127.0.0.1:$ApiPort"
$frontendUrl = "http://127.0.0.1:$WebPort"
$ollamaUrl = "http://127.0.0.1:11434"

Write-Host "ROCmPorter local dev status"
Write-Host "Root: $Root"
if ($state) {
    Write-Host "State: $StateFile"
    Write-Host "Started: $($state.startedAt)"
}
Write-Host ""

Write-Status -Name "Backend" -Url "$backendUrl/api/health" -Ready (Test-HttpOk -Url "$backendUrl/api/health")
Write-Status -Name "Frontend" -Url $frontendUrl -Ready (Test-HttpOk -Url $frontendUrl)
Write-Status -Name "Ollama" -Url "$ollamaUrl/api/tags" -Ready (Test-HttpOk -Url "$ollamaUrl/api/tags")

if ($state) {
    Write-Host ""
    Write-Host "Backend log:  $($state.backend.log)"
    Write-Host "Frontend log: $($state.frontend.log)"
}
