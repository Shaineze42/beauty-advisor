#!/usr/bin/env bash
# Envoie du trafic vers l'API de serving pour alimenter le tableau de bord Grafana.
# Les requêtes invalides (422) servent à montrer la validation des entrées.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${SERVING_PORT:-8010}"
URL="http://127.0.0.1:${PORT}"

echo "Envoi de 40 requêtes valides..."
for i in $(seq 1 40); do
  uid=$(printf "user_%03d" $(( (i % 20) + 1 )))
  curl -s -o /dev/null -X POST "$URL/recommend" -H 'Content-Type: application/json' \
    -d "{\"user_id\": \"${uid}\", \"max_products\": 4}"
done
echo "Envoi de 5 requêtes invalides (identifiant interdit)..."
for i in $(seq 1 5); do
  curl -s -o /dev/null -X POST "$URL/recommend" -H 'Content-Type: application/json' \
    -d '{"user_id": "x y;", "max_products": 4}'
done
echo
echo "Extrait de /metrics :"
curl -s "$URL/metrics" | grep -E '^(ba_requests_total|ba_request_duration_seconds_(sum|count)|ba_model_info|ba_drift_status|ba_drift_psi_max)'
