#!/usr/bin/env bash
# Démarre la pile + l'API de serving du Bloc 4, puis recharge Prometheus et Grafana.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "Fichier .env absent : copiez .env.example vers .env." >&2; exit 1
fi
mkdir -p reports
export COMPOSE_PROFILES=serving
./scripts/dc.sh up -d --build
# Prometheus et Grafana ne relisent leur configuration qu'au redémarrage.
./scripts/dc.sh restart prometheus grafana

PORT="${SERVING_PORT:-8010}"
echo "Attente de l'API de serving..."
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS "http://127.0.0.1:${PORT}/health" && echo
cat <<MSG

API de serving disponible (local uniquement) :
  Documentation  http://127.0.0.1:${PORT}/docs
  Métriques      http://127.0.0.1:${PORT}/metrics
  Prometheus     http://localhost:9090/targets   (job beauty_serving doit être UP)
  Grafana        http://localhost:3000   (tableau de bord « API de serving et dérive »)

Étape suivante : ./scripts/serving_demo.sh
MSG
