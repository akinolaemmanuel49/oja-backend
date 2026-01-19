# scripts/dev-start.ps1
# PowerShell development startup script for FastAPI project
# Uses official fastapi dev CLI with explicit entrypoint

$ErrorActionPreference = "Stop"

Write-Host "Starting development environment..." -ForegroundColor Cyan

# ────────────────────────────────────────────────────────────────────────────────
# 1. Locate virtual environment
# ────────────────────────────────────────────────────────────────────────────────

$possibleVenvPaths = @(".\venv", ".\.venv")
$venvPath = $null

foreach ($path in $possibleVenvPaths) {
    if (Test-Path $path -PathType Container) {
        $venvPath = $path
        break
    }
}

if (-not $venvPath) {
    Write-Host "Error: No virtual environment found." -ForegroundColor Red
    Write-Host "Please create one with:" -ForegroundColor Yellow
    Write-Host "  python -m venv .venv" -ForegroundColor Gray
    exit 1
}

# ────────────────────────────────────────────────────────────────────────────────
# 2. Activate virtual environment
# ────────────────────────────────────────────────────────────────────────────────

$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"

if (-not (Test-Path $activateScript)) {
    Write-Host "Error: Activation script not found at $activateScript" -ForegroundColor Red
    exit 1
}

Write-Host "Activating virtual environment: $venvPath" -ForegroundColor Green
& $activateScript

# Basic activation check
if (-not $env:VIRTUAL_ENV) {
    Write-Host "Warning: Virtual environment activation may have failed." -ForegroundColor Yellow
}

# ────────────────────────────────────────────────────────────────────────────────
# 3. Verify project structure
# ────────────────────────────────────────────────────────────────────────────────

if (-not (Test-Path "src\main.py")) {
    Write-Host "Error: src/main.py not found in project root." -ForegroundColor Red
    exit 1
}

# ────────────────────────────────────────────────────────────────────────────────
# 4. Start FastAPI development server (official CLI)
# ────────────────────────────────────────────────────────────────────────────────

Write-Host "Starting FastAPI dev server..." -ForegroundColor Cyan
Write-Host "Using entrypoint: src.main:app" -ForegroundColor DarkGray

python -m fastapi dev `
    --entrypoint src.main:app `
    --host 0.0.0.0 `
    --port 8000 `
    $args