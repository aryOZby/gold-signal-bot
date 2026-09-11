# Install Python deps on a Windows VPS and create local config files.
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File scripts\vps\setup.ps1

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

Write-Host "Project root: $Root"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python is not on PATH. Install Python 3.11+ and tick 'Add python.exe to PATH'."
}

python -m venv .venv
& "$Root\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "$Root\.venv\Scripts\python.exe" -m pip install -r "$Root\requirements.txt"

if (-not (Test-Path "$Root\config.yaml")) {
    Copy-Item "$Root\config.example.yaml" "$Root\config.yaml"
    Write-Host "Created config.yaml — set dry_run: false and broker.type: mt5_native for live trading"
}
if (-not (Test-Path "$Root\.env")) {
    Copy-Item "$Root\.env.example" "$Root\.env"
    Write-Host "Created .env — fill TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, MT5_*"
}

Write-Host ""
Write-Host "Next:"
Write-Host "  1. Edit .env and config.yaml"
Write-Host "  2. Open MT5, log into a hedging account, keep it running"
Write-Host "  3. .\.venv\Scripts\python.exe scripts\login_telegram.py"
Write-Host "  4. powershell -ExecutionPolicy Bypass -File scripts\vps\install-task.ps1"
