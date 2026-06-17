#!/usr/bin/env bash
# Start MinerU API on Lightning AI Studio.
# After running, open port 8000 in the Studio UI to get your public HTTPS URL.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "No .env found. Run setup_lightning.sh first."
    exit 1
fi

set -a; source "$ENV_FILE"; set +a

# Override paths for Lightning teamspace (persistent storage)
export UPLOAD_DIR="${UPLOAD_DIR:-/teamspace/studios/this_studio/mineru_data/uploads}"
export OUTPUT_DIR="${OUTPUT_DIR:-/teamspace/studios/this_studio/mineru_data/outputs}"
export LOG_DIR="${LOG_DIR:-/teamspace/studios/this_studio/mineru_data/logs}"
mkdir -p "$UPLOAD_DIR" "$OUTPUT_DIR" "$LOG_DIR"

PORT="${PORT:-8000}"
API_KEY=$(grep API_KEY "$ENV_FILE" | grep -v NAME | cut -d= -f2)

echo ""
echo "=== MinerU GPU API — Lightning AI Studio ==="
echo ""
echo "  Backend  : ${MINERU_BACKEND:-hybrid}"
echo "  Effort   : ${MINERU_EFFORT:-high}"
echo "  Workers  : ${PARALLEL_WORKERS:-3} parallel (L40S 48GB)"
echo "  Log file : $LOG_DIR/mineru.log"
echo ""
echo "  API Key  : $API_KEY"
echo ""
echo "  Step 1 → Studio sidebar: click 'Ports' → Add port $PORT → make Public"
echo "  Step 2 → Copy the HTTPS URL shown there"
echo "  Step 3 → Hit: POST <URL>/api/v1/tasks/submit"
echo "           Header: X-API-Key: $API_KEY"
echo ""
echo "  Docs: <URL>/docs"
echo "  Logs: tail -f $LOG_DIR/mineru.log | python3 -m json.tool"
echo ""

cd "$REPO_DIR"
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --workers 1 \
    --timeout-keep-alive 300 \
    --log-level info
