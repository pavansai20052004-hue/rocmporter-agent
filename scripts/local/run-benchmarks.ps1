param(
    [string]$CaseFile = "benchmarks\demo-cases.json",
    [string]$Model = "qwen2.5-coder:latest",
    [string]$Export = "json,md,diff,html,zip,github",
    [string]$Out = ""
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..\..")
$BackendDir = Join-Path $Root "backend"
$BackendPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$ResolvedCaseFile = Join-Path $Root $CaseFile

if (-not (Test-Path $BackendPython)) {
    throw "Backend virtual environment missing. Run backend setup first."
}

if (-not (Test-Path $ResolvedCaseFile)) {
    throw "Benchmark case file not found: $ResolvedCaseFile"
}

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
if ($Out) {
    $OutputDir = if ([System.IO.Path]::IsPathRooted($Out)) { $Out } else { Join-Path $Root $Out }
} else {
    $OutputDir = Join-Path $Root "work\benchmark-runs\$Timestamp"
}

Push-Location $BackendDir
try {
    & $BackendPython "rocmporter.py" benchmark --cases $ResolvedCaseFile --model $Model --export $Export --out $OutputDir
    if ($LASTEXITCODE -ne 0) {
        throw "Benchmark run failed."
    }
} finally {
    Pop-Location
}

Write-Host "Benchmark artifacts: $OutputDir"
