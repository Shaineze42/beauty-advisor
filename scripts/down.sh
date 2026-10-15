#!/usr/bin/env bash
# Arrête la pile. Avec --volumes : supprime aussi les données (bases, Grafana, Prometheus).
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "${1:-}" = "--volumes" ]; then
  ./scripts/dc.sh down --volumes
else
  ./scripts/dc.sh down
fi
