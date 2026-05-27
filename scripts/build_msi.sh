#!/bin/bash
# Build MSI installer for Windows with bundled models
# Usage: ./scripts/build_msi.sh [model_name]
#
# Prerequisites:
#   pip install briefcase
#   Windows with WSL or native Windows Python
#
# This script:
# 1. Downloads the specified model (default: gemma3:1b)
# 2. Bundles it in the MSI installer
# 3. Creates a self-contained installer

set -e

MODEL_NAME="${1:-gemma3:1b}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== YanFu MSI Builder ==="
echo "Model: $MODEL_NAME"
echo ""

# Step 1: Download model
echo "[1/4] Downloading model..."
python "$SCRIPT_DIR/bundle_models.py" --model "$MODEL_NAME" --output "$PROJECT_DIR/models"

# Step 2: Verify model
echo "[2/4] Verifying model..."
MODEL_PATH=$(find "$PROJECT_DIR/models" -name "*.gguf" | head -1)
if [ -z "$MODEL_PATH" ]; then
    echo "Error: No GGUF model found in models/"
    exit 1
fi
MODEL_SIZE=$(du -h "$MODEL_PATH" | cut -f1)
echo "Model: $MODEL_PATH ($MODEL_SIZE)"

# Step 3: Build with Briefcase
echo "[3/4] Building MSI with Briefcase..."
cd "$PROJECT_DIR"
briefcase create windows msi
briefcase build windows msi

# Step 4: Package
echo "[4/4] Creating installer..."
briefcase package windows msi

echo ""
echo "=== Build Complete ==="
echo "MSI installer created in dist/"
echo ""
echo "Installation instructions:"
echo "1. Double-click the MSI file to install"
echo "2. Launch YanFu from Start Menu or Desktop"
echo "3. Models are pre-installed, no download needed"
echo "4. Works completely offline after installation"
