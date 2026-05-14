# ── eStamp Ninja — Build Script ───────────────────────────────────────────────
# Produces a single-file Windows executable in ./dist/eStampNinja.exe
# Run from the project root: .\build.ps1
# Requires: pip install pyinstaller pillow

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot

Write-Host "==> Checking PyInstaller..." -ForegroundColor Cyan
py -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyInstaller..." -ForegroundColor Yellow
    py -m pip install pyinstaller
}

# Convert icon.png → icon.ico (PyInstaller needs .ico on Windows for taskbar icon)
Write-Host "==> Converting icon.png to icon.ico..." -ForegroundColor Cyan
py -c @"
from PIL import Image
img = Image.open(r'$ProjectDir\icon.png')
img.save(r'$ProjectDir\icon.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(32,32),(16,16)])
print('icon.ico created')
"@

Write-Host "==> Building executable..." -ForegroundColor Cyan
py -m PyInstaller `
    --onefile `
    --windowed `
    --name "eStampNinja" `
    --icon "$ProjectDir\icon.ico" `
    --add-data "$ProjectDir\icon.png;." `
    --add-data "$ProjectDir\logo.png;." `
    --add-data "$ProjectDir\config.py;." `
    --hidden-import playwright `
    --hidden-import playwright.sync_api `
    "$ProjectDir\estamp_auto.py"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "==> SUCCESS! Executable at: $ProjectDir\dist\eStampNinja.exe" -ForegroundColor Green
    Write-Host "    Chromium will be auto-installed on first launch if missing." -ForegroundColor Cyan
} else {
    Write-Host "==> Build FAILED. Check errors above." -ForegroundColor Red
}
