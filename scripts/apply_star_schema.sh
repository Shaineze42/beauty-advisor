#!/usr/bin/env bash
# Crée (ou met à jour) le schéma analytique en étoile sur une base déjà initialisée.
# (Sur un volume neuf, le fichier est appliqué automatiquement au démarrage.)
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
./scripts/dc.sh exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" < docker/postgres/02_star_schema.sql
echo "Schéma analytics prêt. Exemple :"
echo "  ./scripts/dc.sh exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -c 'SELECT * FROM analytics.v_interactions_by_category_skin;'"
