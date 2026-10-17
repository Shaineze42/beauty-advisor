#!/usr/bin/env bash
# Démarre la pile + le pipeline temps réel (Redpanda, producteur, Airflow) et attend qu'il soit prêt.
# Demande environ 2 Go de mémoire en plus : au besoin, arrêtez pgAdmin, Mongo Express et Portainer.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "Fichier .env absent : copiez .env.example vers .env." >&2; exit 1
fi
export COMPOSE_PROFILES=pipeline
./scripts/dc.sh up -d --build

echo "Attente d'Airflow (jusqu'à 4 minutes, premier démarrage plus long)..."
for i in $(seq 1 48); do
  status=$(./scripts/dc.sh ps --format '{{.Name}} {{.Health}}' | awk '$1=="beauty_airflow"{print $2}')
  [ "$status" = "healthy" ] && break
  sleep 5
done
./scripts/dc.sh ps --format 'table {{.Name}}\t{{.Status}}' | grep -E "NAME|redpanda|airflow|stream"
set -a; . ./.env; set +a
cat <<MSG

Pipeline disponible (local uniquement) :
  Airflow   http://localhost:${AIRFLOW_PORT:-8085}   (utilisateur admin)
  Grafana   http://localhost:${GRAFANA_PORT:-3000}   (tableau de bord « pipeline temps réel »)

Étape suivante : ./scripts/pipeline_check.sh puis ./scripts/pipeline_demo.sh
MSG
