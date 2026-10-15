#!/usr/bin/env bash
# Vérifie que chaque composant répond. Code de sortie 1 si l'un d'eux est en échec.
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

fail=0
check() {
  local name="$1" url="$2"
  if curl -fsS -m 5 -o /dev/null "$url"; then
    printf "  [OK]   %-22s %s\n" "$name" "$url"
  else
    printf "  [ECHEC] %-21s %s\n" "$name" "$url"
    fail=1
  fi
}

echo "Contrôle de la pile Beauty Advisor"
check "API /health"        "http://localhost:${API_PORT:-8000}/health"
check "API /metrics"       "http://localhost:${API_PORT:-8000}/metrics"
check "Prometheus"         "http://localhost:${PROMETHEUS_PORT:-9090}/-/ready"
check "Grafana"            "http://localhost:${GRAFANA_PORT:-3000}/api/health"

echo
echo "Cibles Prometheus :"
curl -fsS -m 5 "http://localhost:${PROMETHEUS_PORT:-9090}/api/v1/targets" 2>/dev/null | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)["data"]["activeTargets"]
except Exception:
    print("  [ECHEC] réponse illisible"); sys.exit(1)
bad = 0
for t in data:
    ok = t["health"] == "up"
    bad += 0 if ok else 1
    print("  [%s] %-18s %s" % ("OK" if ok else "ECHEC", t["labels"]["job"], t["scrapeUrl"]))
sys.exit(1 if bad else 0)
' || fail=1

echo
echo "Conteneurs :"
./scripts/dc.sh ps --format 'table {{.Name}}\t{{.Status}}' 2>/dev/null || ./scripts/dc.sh ps

echo
if [ "$fail" = "0" ]; then echo "Tout est opérationnel."; else echo "Au moins un composant est en échec."; fi
exit "$fail"
