#!/usr/bin/env python3
"""Exportateur Prometheus de Beauty Advisor (bibliothèque standard uniquement).

Lit l'API d'inférence (/health et /metrics) ainsi que les rapports JSON
(monitoring_report.json, evaluation_personalized_report.json) et expose
le tout au format texte Prometheus sur /metrics (port 9100).
"""
import json
import os
import re
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

API_URL = os.getenv("API_URL", "http://api:8000").rstrip("/")
REPORTS_DIR = Path(os.getenv("REPORTS_DIR", "/reports"))
PORT = int(os.getenv("EXPORTER_PORT", "9100"))
TIMEOUT = 3
DECISIONS = {"ok": 0, "warning": 1, "alert": 2}


def fetch_json(path):
    with urllib.request.urlopen(API_URL + path, timeout=TIMEOUT) as response:
        return response.status, json.load(response)


def read_report(name):
    try:
        return json.loads((REPORTS_DIR / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def flatten(prefix, value, out):
    """Aplatit un dictionnaire imbriqué en (nom, nombre)."""
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        out.append((prefix, float(value)))
    elif isinstance(value, dict):
        for key, item in value.items():
            flatten(f"{prefix}.{key}" if prefix else str(key), item, out)


def label(value):
    return re.sub(r'["\\\n]', "_", str(value))


def line(name, value, labels=None):
    tags = ""
    if labels:
        tags = "{" + ",".join(f'{k}="{label(v)}"' for k, v in labels.items()) + "}"
    return f"{name}{tags} {value}"


def collect():
    out = []

    def metric(name, help_text, kind, samples):
        out.append(f"# HELP {name} {help_text}")
        out.append(f"# TYPE {name} {kind}")
        out.extend(samples)

    started = time.time()
    api_up, service, evaluation, health = 0, {}, {}, {}
    try:
        status, health = fetch_json("/health")
        api_up = 1 if status == 200 else 0
        _, payload = fetch_json("/metrics")
        service = payload.get("service", {})
        evaluation = payload.get("last_evaluation", {})
    except Exception:  # API injoignable : on expose simplement up = 0
        api_up = 0
    scrape_seconds = time.time() - started

    metric("beauty_api_up", "1 si l'API répond sur /health", "gauge", [line("beauty_api_up", api_up)])
    metric("beauty_exporter_scrape_seconds", "Durée de la collecte auprès de l'API", "gauge",
           [line("beauty_exporter_scrape_seconds", round(scrape_seconds, 4))])
    if service:
        metric("beauty_api_requests_total", "Requêtes traitées par l'API", "counter",
               [line("beauty_api_requests_total", service.get("requests_total", 0))])
        metric("beauty_api_errors_total", "Réponses HTTP >= 400", "counter",
               [line("beauty_api_errors_total", service.get("errors_total", 0))])
        metric("beauty_api_average_latency_ms", "Latence moyenne depuis le démarrage (ms)", "gauge",
               [line("beauty_api_average_latency_ms", service.get("average_latency_ms", 0))])
        metric("beauty_api_uptime_seconds", "Durée de fonctionnement de l'API", "gauge",
               [line("beauty_api_uptime_seconds", service.get("uptime_seconds", 0))])
    if health:
        metric("beauty_dataset_users", "Utilisateurs présents dans le jeu de données servi", "gauge",
               [line("beauty_dataset_users", health.get("users", 0))])
        metric("beauty_dataset_products", "Produits présents dans le jeu de données servi", "gauge",
               [line("beauty_dataset_products", health.get("products", 0))])

    samples = []
    for group in ("business_metrics", "diagnostic_metrics"):
        flat = []
        flatten("", evaluation.get(group) or {}, flat)
        samples += [
            line("beauty_evaluation_metric", round(value, 6), {"group": group, "name": name})
            for name, value in flat[:60]
        ]
    if samples:
        metric("beauty_evaluation_metric", "Métriques de la dernière évaluation du moteur", "gauge", samples)

    monitoring = read_report("monitoring_report.json")
    decision = str(monitoring.get("decision") or monitoring.get("status") or "").lower()
    if monitoring:
        metric("beauty_model_monitoring_decision",
               "Décision du suivi du modèle (0 ok, 1 warning, 2 alert, -1 inconnue)", "gauge",
               [line("beauty_model_monitoring_decision", DECISIONS.get(decision, -1))])
    return "\n".join(out) + "\n"


class Handler(BaseHTTPRequestHandler):
    server_version = "BeautyExporter"
    sys_version = ""

    def do_GET(self):
        if self.path == "/metrics":
            body, status, kind = collect().encode("utf-8"), 200, "text/plain; version=0.0.4; charset=utf-8"
        elif self.path == "/healthz":
            body, status, kind = b"ok\n", 200, "text/plain"
        else:
            body, status, kind = b"not found\n", 404, "text/plain"
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
