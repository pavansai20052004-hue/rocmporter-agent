param(
    [string]$Model = "qwen2.5-coder",
    [switch]$RunChecks
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..\..")
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$BackendPython = Join-Path $BackendDir ".venv\Scripts\python.exe"

$Failures = New-Object System.Collections.Generic.List[string]
$Warnings = New-Object System.Collections.Generic.List[string]

function Write-Check {
    param(
        [string]$State,
        [string]$Message
    )

    $prefix = switch ($State) {
        "ok" { "[OK]" }
        "warn" { "[WARN]" }
        "fail" { "[FAIL]" }
        default { "[INFO]" }
    }

    Write-Host "$prefix $Message"
}

function Add-Failure {
    param([string]$Message)
    $Failures.Add($Message) | Out-Null
    Write-Check "fail" $Message
}

function Add-Warning {
    param([string]$Message)
    $Warnings.Add($Message) | Out-Null
    Write-Check "warn" $Message
}

function Test-CommandAvailable {
    param([string]$Name)

    if (Get-Command $Name -ErrorAction SilentlyContinue) {
        Write-Check "ok" "$Name is available"
        return $true
    }

    Add-Failure "$Name is missing from PATH"
    return $false
}

Set-Location $Root
Write-Host "ROCmPorter local readiness"
Write-Host "Root: $Root"
Write-Host ""

$hasGit = Test-CommandAvailable "git"
$hasNode = Test-CommandAvailable "node"
$hasNpm = Test-CommandAvailable "npm"
$hasOllama = Test-CommandAvailable "ollama"

if (Test-Path $BackendPython) {
    Write-Check "ok" "Backend virtual environment found"
    $Python = $BackendPython
} elseif (Get-Command "python" -ErrorAction SilentlyContinue) {
    Add-Warning "Backend virtual environment is missing; using system python for lightweight checks"
    $Python = "python"
} else {
    Add-Failure "Python is missing and backend\.venv was not found"
    $Python = $null
}

if (Test-Path (Join-Path $FrontendDir "node_modules")) {
    Write-Check "ok" "Frontend dependencies are installed"
} else {
    Add-Warning "frontend\node_modules is missing; run npm install inside frontend"
}

if ($hasOllama) {
    try {
        $ollamaList = & ollama list
        $modelNames = @()
        foreach ($line in ($ollamaList | Select-Object -Skip 1)) {
            $name = ($line -split "\s+")[0]
            if ($name) {
                $modelNames += $name
            }
        }

        $requestedNames = @($Model)
        if ($Model -notmatch ":") {
            $requestedNames += "${Model}:latest"
        }

        $foundModel = $false
        foreach ($candidate in $requestedNames) {
            if ($modelNames -contains $candidate) {
                $foundModel = $true
            }
        }

        if ($foundModel) {
            Write-Check "ok" "Ollama model is installed: $Model"
        } else {
            Add-Warning "Ollama is running, but $Model is not installed. Run: ollama pull $Model"
        }
    } catch {
        Add-Failure "Ollama is installed but not reachable. Start Ollama, then run this script again"
    }
}

if ($RunChecks) {
    Write-Host ""
    Write-Host "Running local checks..."

    if ($Python) {
        & $Python -m compileall (Join-Path $BackendDir "app")
        if ($LASTEXITCODE -ne 0) {
            Add-Failure "Backend compile check failed"
        } else {
            Write-Check "ok" "Backend compile check passed"
        }
    }

    if ($hasNpm -and (Test-Path (Join-Path $FrontendDir "node_modules"))) {
        Push-Location $FrontendDir
        try {
            & npm run lint
            if ($LASTEXITCODE -ne 0) {
                Add-Failure "Frontend lint failed"
            } else {
                Write-Check "ok" "Frontend lint passed"
            }

            & npm run test:e2e
            if ($LASTEXITCODE -ne 0) {
                Add-Failure "Frontend smoke tests failed"
            } else {
                Write-Check "ok" "Frontend smoke tests passed"
            }
        } finally {
            Pop-Location
        }
    }
}

Write-Host ""
if ($Failures.Count -gt 0) {
    Write-Host "Local readiness failed with $($Failures.Count) required issue(s)."
    exit 1
}

if ($Warnings.Count -gt 0) {
    Write-Host "Local readiness passed with $($Warnings.Count) warning(s)."
    exit 0
}

Write-Host "Local readiness passed."
