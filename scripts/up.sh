#!/usr/bin/env bash
# Déploie toute la pile (données, application, monitoring) et attend qu'elle soit saine.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "Fichier .env absent : copiez .env.example vers .env et renseignez les mots de passe." >&2
  exit 1
fi
if grep -q "change_me" .env; then
  echo "Attention : .env contient encore des mots de passe 'change_me'." >&2
fi

./scripts/dc.sh up -d --build

echo "Attente des services (jusqu'à 120 s)..."
for i in $(seq 1 24); do
  unhealthy=$(./scripts/dc.sh ps --format '{{.Name}} {{.Health}}' | awk '$2=="starting" || $2=="unhealthy"' | wc -l | tr -d ' ')
  if [ "$unhealthy" = "0" ]; then break; fi
  sleep 5
done

./scripts/dc.sh ps
set -a; . ./.env; set +a
cat <<MSG

Services disponibles (local uniquement) :
  API            http://localhost:${API_PORT:-8000}/health
  Grafana        http://localhost:${GRAFANA_PORT:-3000}   (utilisateur ${GRAFANA_USER:-admin})
  Prometheus     http://localhost:${PROMETHEUS_PORT:-9090}
  pgAdmin        http://localhost:${PGADMIN_PORT}
  Mongo Express  http://localhost:${MONGO_EXPRESS_PORT}
  Portainer      http://localhost:${PORTAINER_PORT}

Étape suivante : ./scripts/check.sh
MSG
