#!/usr/bin/env bash
# Downloads all MinerU 3.3 models into the container's /root/models volume.
# Run once after first `docker compose up`:
#   docker compose exec mineru-api bash /app/scripts/download_models.sh
set -euo pipefail

echo "[mineru] Downloading models (this may take 10-30 min on first run)..."
python3 - <<'EOF'
from mineru.utils.download_models import download_all_models
download_all_models()
print("[mineru] All models downloaded.")
EOF
