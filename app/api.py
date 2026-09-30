"""
API d'inférence Beauty Advisor (bibliothèque standard uniquement).

Endpoints :
  GET /health                               état du service
  GET /recommend?user_id=user_001&max_products=4   routine personnalisée
  GET /metrics                              métriques de service + dernière évaluation
"""
import json
import logging
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from recommendation_engine import build_recommendation, read_features


HOST = os.getenv("API_HOST", "0.0.0.0")
PORT = int(os.getenv("API_PORT", "8000"))

AI_REPORT_PATH = Path("reports/ai_data_report.json")
EVAL_REPORT_PATH = Path("reports/evaluation_personalized_report.json")

USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,50}$")
DEFAULT_MAX_PRODUCTS = 4
MAX_PRODUCTS_LIMIT = 6

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("beauty_api")


def read_json(path):
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


class ServiceState:
    """Compteurs de service partagés entre les requêtes (thread-safe)."""

    def __init__(self, rows):
        self.rows = rows
        self.engine_lock = threading.Lock()
        self.stats_lock = threading.Lock()
        self.requests_total = 0
        self.errors_total = 0
        self.latency_total = 0.0
        self.started_at = time.time()

    def record(self, status, seconds):
        with self.stats_lock:
            self.requests_total += 1
            self.latency_total += seconds
            if status >= 400:
                self.errors_total += 1

    def snapshot(self):
        with self.stats_lock:
            average = (
                self.latency_total / self.requests_total
                if self.requests_total
                else 0.0
            )
            return {
                "requests_total": self.requests_total,
                "errors_total": self.errors_total,
                "average_latency_ms": round(average * 1000, 3),
                "uptime_seconds": round(time.time() - self.started_at, 1),
            }


def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        server_version = "BeautyAdvisor"
        sys_version = ""

        def send_json(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return status

        def handle_health(self):
            meta = read_json(AI_REPORT_PATH)
            return self.send_json(
                200,
                {
                    "status": "ok",
                    "dataset_version": meta.get("dataset_version"),
                    "users": len({row["user_id"] for row in state.rows}),
                    "products": len({row["product_id"] for row in state.rows}),
                },
            )

        def handle_metrics(self):
            evaluation = read_json(EVAL_REPORT_PATH)
            return self.send_json(
                200,
                {
                    "service": state.snapshot(),
                    "last_evaluation": {
                        "dataset_version": evaluation.get("dataset_version"),
                        "business_metrics": evaluation.get("business_metrics"),
                        "diagnostic_metrics": evaluation.get("diagnostic_metrics"),
                    },
                },
            )

        def handle_recommend(self, query):
            user_id = (query.get("user_id") or [""])[0]

            if not USER_ID_PATTERN.match(user_id):
                return self.send_json(
                    400,
                    {"error": "user_id invalide (lettres, chiffres, _ et - ; 50 max)."},
                )

            raw_max = (query.get("max_products") or [str(DEFAULT_MAX_PRODUCTS)])[0]

            if not raw_max.isdigit() or not 1 <= int(raw_max) <= MAX_PRODUCTS_LIMIT:
                return self.send_json(
                    400,
                    {"error": f"max_products doit être compris entre 1 et {MAX_PRODUCTS_LIMIT}."},
                )

            try:
                # Le moteur annote les lignes : un seul calcul à la fois.
                with state.engine_lock:
                    result = build_recommendation(
                        user_id,
                        max_products=int(raw_max),
                        feature_rows=state.rows,
                    )
            except ValueError:
                return self.send_json(404, {"error": "Utilisateur inconnu."})
            except Exception:
                logger.exception("Erreur interne pendant la recommandation")
                return self.send_json(500, {"error": "Erreur interne."})

            return self.send_json(200, result)

        def route(self, method):
            start = time.perf_counter()
            parsed = urlparse(self.path)

            if method != "GET":
                status = self.send_json(405, {"error": "Méthode non autorisée."})
            elif parsed.path == "/health":
                status = self.handle_health()
            elif parsed.path == "/metrics":
                status = self.handle_metrics()
            elif parsed.path == "/recommend":
                status = self.handle_recommend(parse_qs(parsed.query))
            else:
                status = self.send_json(404, {"error": "Route inconnue."})

            seconds = time.perf_counter() - start
            state.record(status, seconds)
            logger.info("%s %s -> %s (%.1f ms)", method, parsed.path, status, seconds * 1000)

        def do_GET(self):
            self.route("GET")

        def do_POST(self):
            self.route("POST")

        def do_PUT(self):
            self.route("PUT")

        def do_DELETE(self):
            self.route("DELETE")

        def log_message(self, format, *args):
            pass

    return Handler


def make_server(rows, host=HOST, port=PORT):
    state = ServiceState(rows)
    return ThreadingHTTPServer((host, port), make_handler(state))


def main():
    rows = read_features()
    server = make_server(rows)
    logger.info("Beauty Advisor API prête sur %s:%s (%s lignes)", HOST, PORT, len(rows))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Arrêt du service")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()