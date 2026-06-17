#!/usr/bin/env bash
# One-shot deploy: build, start, download models
set -euo pipefail

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — set API_KEY before continuing."
  exit 1
fi

docker compose up -d --build
echo "Waiting for container to be healthy..."
sleep 15

echo "Downloading MinerU models (first run only — persisted in Docker volume)..."
docker compose exec mineru-api bash /app/scripts/download_models.sh

echo ""
echo "=== MinerU GPU API ready ==="
echo "Endpoint : http://$(hostname -I | awk '{print $1}'):8000"
echo "API Key  : $(grep API_KEY .env | cut -d= -f2)"
echo "Docs     : http://$(hostname -I | awk '{print $1}'):8000/docs"
