#!/bin/bash
# Build the SigmX desktop client end-to-end.
#
# Step 1: PyInstaller bundle (Python backend + frontend dist)
# Step 2: Copy to desktop/python-dist/
# Step 3: electron-builder NSIS installer
#
# Prerequisites:
#   - Python 3.11+ with pyinstaller installed
#   - Node.js 20+
#   - Frontend dist built (cd frontend && npm run build)
#
# Usage: bash scripts/build-desktop.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "=== SigmX Desktop Builder ==="
echo "Root: $ROOT"

# ---- Step 1: PyInstaller ----
echo ""
echo "[1/3] Building PyInstaller bundle..."
cd "$ROOT"
pyinstaller vibe-trading.spec
echo "  -> dist/vibe-trading/"

# ---- Step 2: Copy to desktop ----
echo ""
echo "[2/3] Copying Python bundle to desktop/python-dist/..."
rm -rf "$ROOT/desktop/python-dist"
mkdir -p "$ROOT/desktop/python-dist"
cp -R "$ROOT/dist/vibe-trading" "$ROOT/desktop/python-dist/vibe-trading"
echo "  -> desktop/python-dist/vibe-trading/"

# ---- Step 3: electron-builder ----
echo ""
echo "[3/3] Building NSIS installer..."
cd "$ROOT/desktop"
npm install
npm run build:win
echo ""
echo "=== Done ==="
echo "Installer: desktop/release/SigmX-Setup-*.exe"
