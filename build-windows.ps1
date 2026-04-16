# Windows Build Script for VFX Shot Tracker
Write-Host "=== VFX Shot Tracker Windows Build Script ===" -ForegroundColor Cyan

# Step 1: Create venv
Write-Host "`n[1/7] Creating Python virtual environment..." -ForegroundColor Yellow
py -3.13 -m venv venv

# Step 2: Activate and install Python deps
Write-Host "[2/7] Installing Python dependencies..." -ForegroundColor Yellow
.\venv\Scripts\pip install flask flask-sqlalchemy pillow opentimelineio opentimelineio-plugins playwright reportlab pyinstaller

# Step 3: Install Playwright browsers
Write-Host "[3/7] Installing Playwright browsers..." -ForegroundColor Yellow
.\venv\Scripts\python -m playwright install chromium

# Step 4: Copy Playwright browsers to project folder for bundling
Write-Host "[4/7] Copying Playwright browsers for bundling..." -ForegroundColor Yellow
if (Test-Path "playwright-browsers") {
    Remove-Item -Recurse -Force "playwright-browsers"
}
New-Item -ItemType Directory -Path "playwright-browsers" -Force | Out-Null
$playwrightPath = "$env:LOCALAPPDATA\ms-playwright"
Get-ChildItem -Path $playwrightPath | Copy-Item -Destination "playwright-browsers" -Recurse -Force
Write-Host "Copied browsers from: $playwrightPath" -ForegroundColor Gray

# Step 5: Create instance folder
Write-Host "[5/7] Creating instance folder..." -ForegroundColor Yellow
if (-not (Test-Path "instance")) {
    New-Item -ItemType Directory -Path "instance"
}

# Step 6: Build Flask server with ALL Playwright dependencies
Write-Host "[6/7] Building Flask server executable..." -ForegroundColor Yellow
.\venv\Scripts\pyinstaller --onefile `
    --add-data "templates;templates" `
    --add-data "static;static" `
    --add-data "instance;instance" `
    --hidden-import flask `
    --hidden-import flask_sqlalchemy `
    --hidden-import sqlalchemy `
    --hidden-import PIL `
    --hidden-import werkzeug `
    --hidden-import opentimelineio `
    --hidden-import opentimelineio.adapters `
    --hidden-import otio_cmx3600_adapter `
    --hidden-import otio_ale_adapter `
    --hidden-import playwright `
    --hidden-import playwright.sync_api `
    --hidden-import playwright._impl `
    --hidden-import playwright._impl._driver `
    --hidden-import greenlet `
    --hidden-import reportlab `
    --hidden-import reportlab.lib `
    --hidden-import reportlab.pdfgen `
    --collect-data opentimelineio `
    --collect-data opentimelineio_contrib `
    --collect-all otio_cmx3600_adapter `
    --collect-all otio_ale_adapter `
    --collect-all playwright `
    --additional-hooks-dir . `
    --name vfx-server app.py

# Step 7: Build Electron app
Write-Host "[7/7] Building Electron application..." -ForegroundColor Yellow
npx electron-builder --win

Write-Host "`n=== Build Complete! ===" -ForegroundColor Green
Write-Host "Installer: dist\VFX Shot Tracker Setup 1.0.0.exe" -ForegroundColor Green
Write-Host "Portable: dist\VFX Shot Tracker 1.0.0.exe" -ForegroundColor Green
Write-Host "`nNote: Final app size is ~400MB due to bundled Playwright browsers" -ForegroundColor Cyan