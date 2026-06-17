#!/usr/bin/env bash
# Start MinerU API server without Docker.
# Must have run setup_bare.sh first.
set -euo pipefail

VENV_DIR="$(pwd)/.venv"
ENV_FILE="${ENV_FILE:-.env}"

if [ ! -f "$ENV_FILE" ]; then
    cp .env.example .env
    echo "Created .env — set API_KEY then re-run."
    exit 1
fi

# Load env vars
set -a; source "$ENV_FILE"; set +a

# Activate venv
source "$VENV_DIR/bin/activate"

echo "[mineru] Starting API server on ${HOST:-0.0.0.0}:${PORT:-8000}"
echo "[mineru] Backend: ${MINERU_BACKEND:-hybrid} | Effort: ${MINERU_EFFORT:-high} | Workers: ${PARALLEL_WORKERS:-2}"

exec uvicorn app.main:app \
    --host "${HOST:-0.0.0.0}" \
    --port "${PORT:-8000}" \
    --workers 1 \
    --timeout-keep-alive 300 \
    --log-level info
