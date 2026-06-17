#!/usr/bin/env bash
# Lightning AI Studio setup — uses conda base env (no venv allowed).
# Run once in the Studio terminal:
#   bash scripts/setup_lightning.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MODELS_DIR="${MODELS_DIR:-/teamspace/studios/this_studio/mineru_models}"

echo "[1/4] Installing PyTorch into conda base (CUDA 12.1)..."
pip install --upgrade pip -q
# Lightning AI has CUDA 12.x — cu121 wheel works
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121 -q

echo "[2/4] Installing MinerU 3.3 + API deps..."
pip install "mineru[all]==3.3.1" -q
pip install fastapi "uvicorn[standard]" python-multipart aiofiles pydantic pydantic-settings -q

echo "[3/4] Writing MinerU config (models → persistent teamspace)..."
mkdir -p "$MODELS_DIR"
python3 - <<PYEOF
import json, os
cfg = json.load(open("$REPO_DIR/config/magic-pdf.json"))
cfg["models-dir"] = "$MODELS_DIR"
dest = os.path.expanduser("~/.magic-pdf.json")
with open(dest, "w") as f:
    json.dump(cfg, f, indent=2)
print(f"Config written to {dest}")
PYEOF

echo "[4/4] Downloading MinerU models to $MODELS_DIR (10-30 min first run)..."
python3 - <<PYEOF
from mineru.utils.download_models import download_all_models
download_all_models()
print("Models ready.")
PYEOF

# Write .env if not present
if [ ! -f "$REPO_DIR/.env" ]; then
    cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
    APIKEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    # macOS sed needs '' after -i, Linux doesn't — handle both
    sed -i'' "s/your-secret-api-key-here/$APIKEY/" "$REPO_DIR/.env" 2>/dev/null || \
    sed -i  "s/your-secret-api-key-here/$APIKEY/" "$REPO_DIR/.env"
    echo ""
    echo "=== .env created ==="
    echo "API_KEY: $APIKEY   ← save this"
fi

echo ""
echo "=== Setup complete ==="
echo "Next: bash scripts/run_lightning.sh"
