#!/bin/bash
set -e

echo "=== VFX Shot Tracker Mac Build Script ==="

echo "[1/5] Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

echo "[2/5] Installing Python dependencies..."
./venv/bin/pip install --upgrade pip
./venv/bin/pip install flask flask-sqlalchemy pillow opentimelineio opentimelineio-plugins playwright reportlab

echo "[3/5] Installing Playwright Chromium..."
./venv/bin/python -m playwright install chromium

echo "[4/5] Copying Playwright browsers for bundling..."
rm -rf playwright-browsers
mkdir -p playwright-browsers
cp -R ~/Library/Caches/ms-playwright/* playwright-browsers/
echo "Copied browsers from ~/Library/Caches/ms-playwright"

echo "[5/5] Building Electron app..."
npm run build

echo ""
echo "=== Build Complete! ==="
echo "DMG: dist/VFX Shot Tracker-*.dmg"
