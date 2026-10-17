#!/usr/bin/env bash
# Vérifie le pipeline : flux, orchestrateur, métriques. Code de sortie 1 en cas d'échec.
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
fail=0
ok()  { printf "  [OK]    %s\n" "$1"; }
ko()  { printf "  [ECHEC] %s\n" "$1"; fail=1; }

echo "Contrôle du pipeline temps réel"
curl -fsS -m 5 -o /dev/null "http://localhost:${AIRFLOW_PORT:-8085}/health" && ok "Airflow (ordonnanceur et web)" || ko "Airflow"
docker exec beauty_redpanda rpk cluster health 2>/dev/null | grep -q 'Healthy:.*true' && ok "Redpanda (flux Kafka)" || ko "Redpanda"
docker ps --format '{{.Names}}' | grep -q '^beauty_stream_producer$' && ok "Producteur d'événements" || ko "Producteur"

echo
echo "Topic et retard du consommateur :"
docker exec beauty_redpanda rpk topic describe interactions.raw -p 2>/dev/null | head -6 || ko "topic absent"
docker exec beauty_redpanda rpk group describe beauty-ingest 2>/dev/null | head -8 || echo "  (groupe créé au premier run)"

echo
echo "Métriques du pipeline dans Prometheus :"
for m in pipeline_last_run_ok pipeline_freshness_seconds_since_last_run pipeline_totals_runs; do
  v=$(curl -fsS -m 5 "http://localhost:${PROMETHEUS_PORT:-9090}/api/v1/query?query=$m" 2>/dev/null \
      | python3 -c 'import json,sys; r=json.load(sys.stdin)["data"]["result"]; print(r[0]["value"][1] if r else "")' 2>/dev/null)
  if [ -n "$v" ]; then printf "  [OK]    %-45s %s\n" "$m" "$v"; else ko "$m (aucune valeur : attendre le premier run)"; fi
done

echo
if [ "$fail" = "0" ]; then echo "Pipeline opérationnel."; else echo "Au moins un composant est en échec."; fi
exit "$fail"
