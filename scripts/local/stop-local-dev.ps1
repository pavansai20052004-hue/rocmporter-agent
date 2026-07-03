param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5178,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..\..")
$StateFile = Join-Path $Root "work\local-dev\state.json"

function Stop-ProcessIfRunning {
    param(
        [int]$ProcessId,
        [string]$Reason
    )

    if (-not $ProcessId) {
        return
    }

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process) {
        return
    }

    if ($DryRun) {
        Write-Host "[DRY] Would stop PID $ProcessId ($($process.ProcessName)) - $Reason"
        return
    }

    Stop-Process -Id $ProcessId -Force
    Write-Host "[OK] Stopped PID $ProcessId ($($process.ProcessName)) - $Reason"
}

function Stop-PortOwner {
    param(
        [int]$Port
    )

    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    $ownerIds = @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($ownerId in $ownerIds) {
        Stop-ProcessIfRunning -ProcessId ([int]$ownerId) -Reason "listening on port $Port"
    }
}

$state = $null
if (Test-Path $StateFile) {
    $state = Get-Content -Raw $StateFile | ConvertFrom-Json
    $ApiPort = [int]$state.backend.port
    $WebPort = [int]$state.frontend.port
}

Write-Host "Stopping ROCmPorter local dev"
if ($state) {
    Write-Host "State: $StateFile"
}

if ($state) {
    Stop-ProcessIfRunning -ProcessId ([int]$state.backend.pid) -Reason "recorded backend launcher"
    Stop-ProcessIfRunning -ProcessId ([int]$state.frontend.pid) -Reason "recorded frontend launcher"
}

Stop-PortOwner -Port $ApiPort
Stop-PortOwner -Port $WebPort

if ((Test-Path $StateFile) -and -not $DryRun) {
    Remove-Item -LiteralPath $StateFile -Force
}

if ($DryRun) {
    Write-Host "Dry run complete. No processes were stopped."
} else {
    Write-Host "ROCmPorter local dev stopped."
}
