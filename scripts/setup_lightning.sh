#!/usr/bin/env bash
# Lightning AI Studio setup — no Docker, no apt-get, CUDA pre-installed.
# Run once in the Studio terminal:
#   bash scripts/setup_lightning.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# Use Lightning's persistent teamspace so models survive Studio restarts
MODELS_DIR="${MODELS_DIR:-/teamspace/studios/this_studio/mineru_models}"
VENV_DIR="$REPO_DIR/.venv"

echo "[1/5] Creating Python venv..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "[2/5] Installing PyTorch (CUDA 12.1 — Lightning default)..."
pip install --upgrade pip -q
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121 -q

echo "[3/5] Installing MinerU 3.3 + API deps..."
pip install "mineru[all]==3.3.1" -q
pip install fastapi "uvicorn[standard]" python-multipart aiofiles pydantic pydantic-settings -q

echo "[4/5] Writing MinerU config..."
mkdir -p "$MODELS_DIR"
# Patch models-dir to persistent teamspace path
python3 -c "
import json, os, shutil
cfg = json.load(open('$REPO_DIR/config/magic-pdf.json'))
cfg['models-dir'] = '$MODELS_DIR'
dest = os.path.expanduser('~/.magic-pdf.json')
json.dump(cfg, open(dest, 'w'), indent=2)
print(f'Config written to {dest}')
"

echo "[5/5] Downloading MinerU models to $MODELS_DIR (10-30 min first run)..."
python3 -c "
from mineru.utils.download_models import download_all_models
download_all_models()
print('Models ready.')
"

# Write .env if not present
if [ ! -f "$REPO_DIR/.env" ]; then
    cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
    # Generate a random API key
    APIKEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    sed -i "s/your-secret-api-key-here/$APIKEY/" "$REPO_DIR/.env"
    echo ""
    echo "=== .env created with random API key ==="
    echo "API_KEY: $APIKEY"
    echo "Save this — it's your auth key."
fi

echo ""
echo "=== Setup complete ==="
echo "Next: bash scripts/run_lightning.sh"
