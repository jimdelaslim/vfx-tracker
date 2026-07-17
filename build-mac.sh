#!/bin/bash
set -e

echo "=== VFX Shot Tracker Mac Build Script ==="

# Number of previous builds to retain in dist-archive/mac/
KEEP_BUILDS=5
ARCHIVE_DIR="dist-archive/mac"

# Clean previous build output
rm -rf dist

echo "[1/6] Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

echo "[2/6] Installing Python dependencies..."
./venv/bin/pip install --upgrade pip
./venv/bin/pip install flask flask-sqlalchemy pillow opentimelineio opentimelineio-plugins playwright reportlab

echo "[3/6] Installing Playwright Chromium..."
./venv/bin/python -m playwright install chromium

echo "[4/6] Copying Playwright browsers for bundling..."
rm -rf playwright-browsers
mkdir -p playwright-browsers
cp -R ~/Library/Caches/ms-playwright/* playwright-browsers/
echo "Copied browsers from ~/Library/Caches/ms-playwright"

echo "[5/6] Building Electron app..."
npm run build

echo "[6/6] Archiving build artifacts..."
mkdir -p "$ARCHIVE_DIR"
for f in dist/*.dmg; do
    [ -e "$f" ] || continue
    cp "$f" "$ARCHIVE_DIR/"
    echo "Archived: $(basename "$f") -> $ARCHIVE_DIR/"
done

ls -t "$ARCHIVE_DIR"/*.dmg 2>/dev/null | tail -n +$((KEEP_BUILDS + 1)) | while read -r old; do
    echo "Pruned (keep last $KEEP_BUILDS): $(basename "$old")"
    rm -f "$old"
done

echo ""
echo "=== Build Complete! ==="
echo "DMG: dist/VFX Shot Tracker-*.dmg"
echo "Archive: $ARCHIVE_DIR/"
