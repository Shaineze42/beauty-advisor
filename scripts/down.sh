#!/usr/bin/env bash
# Arrête la pile (y compris le pipeline). Avec --volumes : supprime aussi les données
# (bases, Grafana, Prometheus, flux Kafka, base Airflow).
set -euo pipefail
cd "$(dirname "$0")/.."
export COMPOSE_PROFILES=pipeline
if [ "${1:-}" = "--volumes" ]; then
  ./scripts/dc.sh down --volumes
else
  ./scripts/dc.sh down
fi
