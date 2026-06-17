#!/usr/bin/env bash
# Lightning AI Studio setup — conda base env, CUDA 12.x, L40S (sm_89).
# Run once:  bash scripts/setup_lightning.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MODELS_DIR="${MODELS_DIR:-/teamspace/studios/this_studio/mineru_models}"

# Detect CUDA version Lightning is running
CUDA_VER=$(python3 -c "
import subprocess, re
try:
    o = subprocess.check_output(['nvcc','--version'], text=True)
    m = re.search(r'release (\d+\.\d+)', o)
    print(m.group(1) if m else '12.1')
except:
    print('12.1')
" 2>/dev/null || echo "12.1")
CUDA_TAG="cu$(echo $CUDA_VER | tr -d '.')"
echo "CUDA $CUDA_VER → wheel tag $CUDA_TAG"

echo "[1/6] Upgrading pip..."
pip install --upgrade pip -q

echo "[2/6] PyTorch ($CUDA_TAG)..."
pip install torch torchvision --index-url "https://download.pytorch.org/whl/$CUDA_TAG" -q

echo "[3/6] MinerU 3.3 + API deps..."
# Let mineru pull numpy>=2 (needed by opencv 4.13).
# matplotlib/scipy/sklearn on Lightning base show resolver warnings — harmless at runtime.
pip install "mineru[all]==3.3.1" -q
pip install fastapi "uvicorn[standard]" python-multipart aiofiles pydantic pydantic-settings -q

echo "[4/6] Flash Attention 2 (L40S sm_89, CUDA 12.x — no CUDA 13 needed)..."
FA2_OK=0
pip install flash-attn --no-build-isolation -q 2>/dev/null && FA2_OK=1 || true
if [ "$FA2_OK" -eq 0 ]; then
    echo "  Prebuilt wheel not found — compiling (~10 min)..."
    MAX_JOBS=4 pip install flash-attn --no-build-isolation 2>&1 | tail -3 && FA2_OK=1 || true
fi
[ "$FA2_OK" -eq 1 ] && echo "  FA2 installed" || echo "  FA2 skipped — will use sdpa fallback"

echo "[5/6] MinerU config (models → persistent teamspace)..."
mkdir -p "$MODELS_DIR"
python3 - <<PYEOF
import json, os
cfg = json.load(open("$REPO_DIR/config/magic-pdf.json"))
cfg["models-dir"] = "$MODELS_DIR"
# Pick best available attention impl
try:
    import flash_attn
    attn = "flash_attention_2"
except ImportError:
    attn = "sdpa"
cfg.setdefault("vlm-config", {})["attn_implementation"] = attn
dest = "/teamspace/studios/this_studio/.magic-pdf.json"
with open(dest, "w") as f:
    json.dump(cfg, f, indent=2)
print(f"Config → {dest}  (attn={attn})")
PYEOF

echo "[6/6] Downloading MinerU models → $MODELS_DIR ..."
python3 - <<PYEOF
import subprocess, sys

# Try known module paths across MinerU versions
attempts = [
    "from mineru.utils.models_download_utils import download_all_models; download_all_models()",
    "from mineru.utils.download_models import download_all_models; download_all_models()",
    "from mineru.model.model_list import download_all_models; download_all_models()",
]
for code in attempts:
    try:
        exec(code)
        print("Models downloaded via Python API.")
        sys.exit(0)
    except (ImportError, AttributeError):
        continue

# Fallback: CLI command
for cmd in ["mineru-models-download", "mineru download-models"]:
    try:
        r = subprocess.run(cmd.split(), check=True)
        print(f"Models downloaded via: {cmd}")
        sys.exit(0)
    except (FileNotFoundError, subprocess.CalledProcessError):
        continue

# Last resort: huggingface hub
print("Falling back to huggingface_hub download...")
from huggingface_hub import snapshot_download
import os
models_dir = "$MODELS_DIR"
snapshot_download(
    repo_id="opendatalab/MinerU3.3-VLM",
    local_dir=os.path.join(models_dir, "MinerU3.3-VLM"),
    ignore_patterns=["*.md", "*.txt"],
)
print("Models downloaded via huggingface_hub.")
PYEOF

if [ ! -f "$REPO_DIR/.env" ]; then
    cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
    APIKEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    sed -i "s/your-secret-api-key-here/$APIKEY/" "$REPO_DIR/.env"
    echo ""
    echo "=== .env created ==="
    echo "API_KEY: $APIKEY   ← save this"
fi

echo ""
echo "=== Setup complete ==="
echo "Run: bash scripts/run_lightning.sh"
