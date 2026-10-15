#!/usr/bin/env bash
# Raccourci docker compose : même fichier, même .env, depuis n'importe où.
# Exemple : ./scripts/dc.sh exec app python run_bloc4.py
set -euo pipefail
cd "$(dirname "$0")/.."
exec docker compose --env-file .env -f docker/docker-compose.yml "$@"
