# scripts/dev-start.ps1
# PowerShell development startup script for FastAPI project

$ErrorActionPreference = "Stop"

$EmojiIcon = [System.Convert]::toInt32("2714",16)

Write-Host "Welcome to oja-backend server " -ForegroundColor Magenta -NoNewline
Write-Host ([System.Char]::ConvertFromUtf32($EmojiIcon))
Write-Host "Starting development environment..." -ForegroundColor Cyan

# ────────────────────────────────────────────────────────────────────────────────
# 1. Locate virtual environment
# ────────────────────────────────────────────────────────────────────────────────
$possibleVenvPaths = @(".\venv", ".\.venv")
$venvPath = $possibleVenvPaths | Where-Object { Test-Path $_ -PathType Container } | Select-Object -First 1

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

# ────────────────────────────────────────────────────────────────────────────────
# 3. Verify project structure
# ────────────────────────────────────────────────────────────────────────────────
if (-not (Test-Path "src\main.py")) {
    Write-Host "Error: src/main.py not found in project root." -ForegroundColor Red
    exit 1
}

# ────────────────────────────────────────────────────────────────────────────────
# 4. Migrate database
# ────────────────────────────────────────────────────────────────────────────────
python -m alembic upgrade head

# ────────────────────────────────────────────────────────────────────────────────
# 5. Start FastAPI development server
# ────────────────────────────────────────────────────────────────────────────────
Write-Host "Starting FastAPI dev server..." -ForegroundColor Cyan
Write-Host "Entrypoint: src.main:app" -ForegroundColor DarkGray

python -m fastapi dev `
    --entrypoint src.main:app `
    --host 0.0.0.0 `
    --port 8000 `
    $args
