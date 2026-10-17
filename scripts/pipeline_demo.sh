#!/usr/bin/env bash
# Démonstration du pipeline : rafale d'événements, déclenchement du DAG, résultats en base.
#   ./scripts/pipeline_demo.sh             rafale de 20 000 événements (10 % dégradés)
#   ./scripts/pipeline_demo.sh --dirty     rafale très dégradée (60 %) : le portail qualité doit échouer
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
export COMPOSE_PROFILES=pipeline

DIRTY=0.10; EVENTS=20000
if [ "${1:-}" = "--dirty" ]; then DIRTY=0.60; EVENTS=5000; fi
psql() { docker exec beauty_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -P pager=off "$@"; }

echo "1/4  Rafale de ${EVENTS} événements (${DIRTY} dégradés) dans le flux..."
./scripts/dc.sh run --rm -T -e STREAM_RATE=2000 -e MAX_EVENTS="$EVENTS" -e DIRTY_RATIO="$DIRTY" stream-producer 2>&1 | tail -2

start=$(psql -tA -c "SELECT now()")
echo
echo "2/4  Déclenchement du DAG beauty_stream_pipeline..."
docker exec beauty_airflow airflow dags trigger beauty_stream_pipeline >/dev/null

echo "3/4  Attente de la fin du run (jusqu'à 3 minutes)..."
for i in $(seq 1 36); do
  n=$(psql -tA -c "SELECT COUNT(*) FROM pipeline.runs WHERE finished_at > '$start'")
  [ "$n" -ge 1 ] && break
  sleep 5
done

echo
echo "4/4  Résultats"
echo "--- Derniers runs"
psql -c "SELECT right(run_id, 24) AS run, status, consumed, loaded, corrected, rejected, duplicates, lag FROM pipeline.runs ORDER BY started_at DESC LIMIT 4"
echo "--- Contrôles qualité du dernier run"
psql -c "SELECT check_name, round(value::numeric, 3) AS valeur, threshold AS seuil, passed AS ok FROM pipeline.quality_checks WHERE run_id = (SELECT run_id FROM pipeline.runs ORDER BY started_at DESC LIMIT 1) ORDER BY check_name"
echo "--- Quarantaine par raison"
psql -c "SELECT reason, COUNT(*) AS evenements FROM pipeline.quarantine GROUP BY reason ORDER BY evenements DESC"
echo "--- Agrégat analytique (SQL)"
psql -c "SELECT minute, category, interaction_type, interactions, avg_rating FROM analytics.interactions_per_minute ORDER BY minute DESC, interactions DESC LIMIT 6"
