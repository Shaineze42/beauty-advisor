#!/usr/bin/env bash
# Génère du trafic pour la démonstration : le tableau de bord Grafana bouge en direct.
# Usage : ./scripts/demo.sh [nombre_de_tours]   (20 tours par défaut)
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
API="http://localhost:${API_PORT:-8000}"
ROUNDS="${1:-20}"

echo "Trafic de démonstration : $ROUNDS tours (requêtes valides + quelques erreurs volontaires)"
for i in $(seq 1 "$ROUNDS"); do
  user=$(printf "user_%03d" $(( (i % 20) + 1 )))
  curl -s -o /dev/null -w "recommend %s -> %{http_code}\n" "$API/recommend?user_id=$user&max_products=4" | sed "s/%s/$user/"
  if [ $((i % 5)) -eq 0 ]; then
    curl -s -o /dev/null -w "recommend inconnu  -> %{http_code} (attendu 404)\n" "$API/recommend?user_id=inconnu_999"
    curl -s -o /dev/null -w "recommend invalide -> %{http_code} (attendu 400)\n" "$API/recommend?user_id=a%20b"
  fi
  sleep 0.5
done
echo "Terminé. Ouvrez Grafana : les requêtes et les erreurs apparaissent sous quelques secondes."
