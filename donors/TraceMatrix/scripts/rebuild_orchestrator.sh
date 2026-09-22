#!/usr/bin/env bash
set -euo pipefail

# Rebuild and restart the orchestrator container (Unix/WSL)

echo "Stopping orchestrator..."
docker compose stop orchestrator || true

echo "Building orchestrator..."
docker compose build orchestrator

echo "Starting orchestrator..."
docker compose up -d orchestrator

echo "Waiting briefly..."
sleep 5

echo "Showing orchestrator status and recent logs..."
docker compose ps orchestrator || true
docker compose logs --tail=50 orchestrator || true

echo
cat <<'EOT'
Try:
  curl -sf http://localhost:8000/ | jq .
  curl -sf http://localhost:8000/docs | head -n 1
EOT

