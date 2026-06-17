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

echo "[4/6] Flash Attention 2 (prebuilt wheel only — no compile)..."
FA2_OK=0
pip install flash-attn --no-build-isolation -q 2>/dev/null && FA2_OK=1 || true
[ "$FA2_OK" -eq 1 ] && echo "  FA2 installed" || echo "  No prebuilt FA2 wheel — sdpa fallback (still GPU-accelerated)"

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
# download_all_models() prompts interactively — pipe "modelscope" to stdin.
# modelscope: no auth needed. opendatalab models are primary there.
python3 - <<'PYEOF'
import subprocess, sys, os

modules = [
    "mineru.utils.models_download_utils",
    "mineru.utils.download_models",
    "mineru.model.model_list",
]

fn_name = None
mod_name = None
for m in modules:
    try:
        mod = __import__(m, fromlist=["download_all_models"])
        if hasattr(mod, "download_all_models"):
            fn_name = "download_all_models"
            mod_name = m
            break
    except ImportError:
        continue

if fn_name:
    print(f"Using {mod_name}.{fn_name} (auto-selecting modelscope)...")
    # Pipe "modelscope" to answer the interactive source prompt
    # Two prompts: source (modelscope/huggingface) + type (pipeline/vlm/all)
    result = subprocess.run(
        [sys.executable, "-c",
         f"from {mod_name} import {fn_name}; {fn_name}()"],
        input="modelscope\nall\n",
        text=True,
    )
    if result.returncode == 0:
        print("Models downloaded via modelscope.")
        sys.exit(0)
    print("modelscope attempt failed, trying huggingface...")
    result2 = subprocess.run(
        [sys.executable, "-c",
         f"from {mod_name} import {fn_name}; {fn_name}()"],
        input="huggingface\nall\n",
        text=True,
    )
    if result2.returncode == 0:
        print("Models downloaded via huggingface.")
        sys.exit(0)

# CLI fallback
for cmd in ["mineru-models-download", "mineru-models download"]:
    try:
        r = subprocess.run(cmd.split(), input="modelscope\nall\n", text=True)
        if r.returncode == 0:
            print(f"Models downloaded via: {cmd}")
            sys.exit(0)
    except FileNotFoundError:
        continue

print("ERROR: Could not download models. Check logs above.")
sys.exit(1)
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
