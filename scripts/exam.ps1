[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Position = 0)]
    [ValidateSet('preflight', 'start', 'reset', 'test', 'starter', 'verify-data', 'help')]
    [string]$Command = 'help',
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8000,
    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = 'Stop'
$materialRoot = Split-Path -Parent $PSScriptRoot
$materialBackend = Join-Path $materialRoot 'app/backend'
$materialFrontend = Join-Path $materialRoot 'app/frontend'
$materialData = Join-Path $materialRoot 'runtime/data'
$materialLogs = Join-Path $materialRoot 'runtime/logs'
$materialCache = Join-Path $materialRoot 'runtime/cache'
$materialPytestCache = Join-Path $materialCache 'pytest'
$previousUvCache = $env:UV_CACHE_DIR
$previousNpmCache = $env:npm_config_cache
$previousApiTarget = $env:VITE_API_TARGET
$previousDatabaseUrl = $env:DATABASE_URL

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments, [string]$WorkingDirectory)
    Push-Location -LiteralPath $WorkingDirectory
    try {
        & $Executable @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$Executable failed with exit code $LASTEXITCODE"
        }
    }
    finally { Pop-Location }
}

function Prepare-Backend {
    Invoke-Checked -Executable 'uv' -Arguments @('sync', '--frozen', '--quiet') -WorkingDirectory $materialBackend
}

function Prepare-Frontend {
    if (-not (Test-Path -LiteralPath (Join-Path $materialFrontend 'node_modules'))) {
        Invoke-Checked -Executable 'npm.cmd' -Arguments @('ci', '--no-audit', '--no-fund') -WorkingDirectory $materialFrontend
    }
}

function Stop-MaterialProcess {
    param($Process)
    if ($null -ne $Process) {
        $Process.Refresh()
        if (-not $Process.HasExited) {
            & taskkill.exe /PID $Process.Id /T /F 2>$null | Out-Null
        }
    }
}

try {
    if (-not $env:UV_CACHE_DIR) { $env:UV_CACHE_DIR = Join-Path $materialCache 'uv' }
    if (-not $env:npm_config_cache) { $env:npm_config_cache = Join-Path $materialCache 'npm' }
    if ($Command -in @('test', 'starter')) {
        New-Item -ItemType Directory -Path (Join-Path $materialCache 'pytest-tmp') -Force | Out-Null
    }
    if ($Command -in @('start', 'reset')) {
        if (-not $env:DATABASE_URL) {
            New-Item -ItemType Directory -Path $materialData -Force | Out-Null
            $sharedDatabase = (Join-Path $materialData 'materialops.db').Replace('\', '/')
            $env:DATABASE_URL = "sqlite:///$sharedDatabase"
        }
        Write-Host 'Using the shared application database (start preserves initialized data; reset reloads the selected dataset).'
    }

    switch ($Command) {
        'preflight' {
            $materialMissing = @()
            foreach ($materialExecutable in @('uv', 'node', 'npm.cmd')) {
                if (Get-Command $materialExecutable -ErrorAction SilentlyContinue) {
                    Write-Host "[ok] $materialExecutable"
                }
                else {
                    Write-Host "[missing] $materialExecutable"
                    $materialMissing += $materialExecutable
                }
            }
            if ($materialMissing.Count -gt 0) { throw 'Install the missing tools before starting the exam.' }
        }
        'reset' {
            Prepare-Backend
            Invoke-Checked -Executable 'uv' -Arguments @('run', 'python', '-m', 'materialops.cli', 'reset') -WorkingDirectory $materialBackend
        }
        'test' {
            Prepare-Backend
            Prepare-Frontend
            Invoke-Checked -Executable 'uv' -Arguments @('run', 'pytest', '--basetemp', (Join-Path $materialCache 'pytest-tmp/backend')) -WorkingDirectory $materialBackend
            Invoke-Checked -Executable 'uv' -Arguments @('run', 'pytest', '../../scripts/tests', '--basetemp', (Join-Path $materialCache 'pytest-tmp/resources'), '-o', "cache_dir=$materialPytestCache") -WorkingDirectory $materialBackend
            Invoke-Checked -Executable 'npm.cmd' -Arguments @('test') -WorkingDirectory $materialFrontend
            Invoke-Checked -Executable 'npm.cmd' -Arguments @('run', 'build') -WorkingDirectory $materialFrontend
        }
        'starter' {
            Prepare-Backend
            Invoke-Checked -Executable 'uv' -Arguments @('run', 'pytest', '-m', 'starter', '--basetemp', (Join-Path $materialCache 'pytest-tmp/starter'), '-q') -WorkingDirectory $materialBackend
        }
        'verify-data' {
            Prepare-Backend
            Invoke-Checked -Executable 'uv' -Arguments @('run', 'python', '../../scripts/verify_resources.py') -WorkingDirectory $materialBackend
        }
        'start' {
            Prepare-Backend
            Prepare-Frontend
            Invoke-Checked -Executable 'uv' -Arguments @('run', 'python', '-m', 'materialops.cli', 'seed') -WorkingDirectory $materialBackend
            New-Item -ItemType Directory -Path $materialLogs -Force | Out-Null
            $env:VITE_API_TARGET = "http://127.0.0.1:$BackendPort"
            $materialApiProcess = $null
            $materialWebProcess = $null
            try {
                $materialApiProcess = Start-Process -FilePath (Get-Command uv).Source `
                    -ArgumentList @('run', 'uvicorn', 'materialops.main:app', '--host', '127.0.0.1', '--port', "$BackendPort") `
                    -WorkingDirectory $materialBackend -WindowStyle Hidden -PassThru `
                    -RedirectStandardOutput (Join-Path $materialLogs 'backend.stdout.log') `
                    -RedirectStandardError (Join-Path $materialLogs 'backend.stderr.log')
                $materialWebProcess = Start-Process -FilePath (Get-Command node).Source `
                    -ArgumentList @('node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', "$FrontendPort", '--strictPort') `
                    -WorkingDirectory $materialFrontend -WindowStyle Hidden -PassThru `
                    -RedirectStandardOutput (Join-Path $materialLogs 'frontend.stdout.log') `
                    -RedirectStandardError (Join-Path $materialLogs 'frontend.stderr.log')
                Write-Host "MaterialOps: http://127.0.0.1:$FrontendPort"
                Write-Host "API: http://127.0.0.1:$BackendPort/docs"
                Write-Host 'Press Ctrl+C to stop. Service logs are in runtime/logs/.'
                while (-not $materialApiProcess.HasExited -and -not $materialWebProcess.HasExited) {
                    Start-Sleep -Milliseconds 500
                    $materialApiProcess.Refresh()
                    $materialWebProcess.Refresh()
                }
                throw 'A service exited. Check runtime/logs/backend.stderr.log and frontend.stderr.log.'
            }
            finally {
                Stop-MaterialProcess -Process $materialApiProcess
                Stop-MaterialProcess -Process $materialWebProcess
            }
        }
        default { Write-Host '.\exam.ps1 {preflight|start|reset|test|starter|verify-data} [-BackendPort 8000] [-FrontendPort 5173]' }
    }
}
finally {
    $env:UV_CACHE_DIR = $previousUvCache
    $env:npm_config_cache = $previousNpmCache
    $env:VITE_API_TARGET = $previousApiTarget
    $env:DATABASE_URL = $previousDatabaseUrl
}
