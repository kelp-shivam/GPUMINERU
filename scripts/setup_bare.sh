#!/usr/bin/env bash
# Bare-metal setup (no Docker).
# Tested on Ubuntu 22.04 + CUDA 12.4 + Python 3.11.
# Run once on the GPU machine:
#   bash scripts/setup_bare.sh
set -euo pipefail

VENV_DIR="$(pwd)/.venv"
MODELS_DIR="${MODELS_DIR:-/root/models}"
MINERU_CONFIG_DIR="$HOME"

echo "[1/6] System dependencies..."
apt-get update -qq && apt-get install -y --no-install-recommends \
    python3.11 python3.11-dev python3.11-venv python3-pip \
    libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 \
    wget curl git ca-certificates

echo "[2/6] Python venv..."
python3.11 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "[3/6] PyTorch (cu124)..."
pip install --upgrade pip
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124

echo "[4/6] MinerU 3.3 + API server deps..."
pip install "mineru[all]==3.3.1"
pip install fastapi "uvicorn[standard]" python-multipart aiofiles pydantic pydantic-settings

echo "[5/6] MinerU model config..."
cp config/magic-pdf.json "$MINERU_CONFIG_DIR/magic-pdf.json"
mkdir -p "$MODELS_DIR"

echo "[6/6] Downloading MinerU models (10-30 min first run)..."
python3 -c "
from mineru.utils.download_models import download_all_models
download_all_models()
print('Models downloaded.')
"

echo ""
echo "=== Bare-metal setup complete ==="
echo "Start API: bash scripts/run_bare.sh"
