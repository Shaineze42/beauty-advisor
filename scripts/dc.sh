#!/usr/bin/env bash
# Raccourci docker compose : mêmes fichiers, même .env, depuis n'importe où.
# Les services du pipeline temps réel sont dans le profil "pipeline" (voir pipeline_up.sh).
# Exemple : ./scripts/dc.sh exec app python run_bloc4.py
set -euo pipefail
cd "$(dirname "$0")/.."
exec docker compose --env-file .env \
  -f docker/docker-compose.yml -f docker/docker-compose.pipeline.yml "$@"
