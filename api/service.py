"""Logique de serving, indépendante du framework web (testable sans FastAPI)."""
import json
import os
import sys
import threading
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"
# En dernier : app/ contient un ancien api.py qui ne doit pas masquer ce paquet.
if str(APP_DIR) not in sys.path:
    sys.path.append(str(APP_DIR))

import recommendation_engine as engine  # noqa: E402

USER_ID_PATTERN = r"^[A-Za-z0-9_-]{1,50}$"
DEFAULT_MAX_PRODUCTS = 4
MAX_PRODUCTS_LIMIT = 6
AI_REPORT_PATH = Path("reports/ai_data_report.json")
# Rapport écrit par monitoring/drift.py ; chemin surchargeable par BA_DRIFT_REPORT.
DEFAULT_DRIFT_REPORT = "reports/drift_report.json"
DRIFT_LEVELS = {"stable": 0, "warning": 1, "drift": 2}


class UnknownUser(Exception):
    """L'utilisateur demandé n'existe pas dans les données."""


def read_json(path):
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def drift_metric_lines(path=None):
    """Métriques de dérive (format Prometheus) lues dans le rapport de monitoring/drift.py.

    Si le rapport est absent ou illisible, seule ba_drift_report_available vaut 0 :
    le service continue de répondre normalement.
    """
    path = Path(path or os.environ.get("BA_DRIFT_REPORT", DEFAULT_DRIFT_REPORT))
    report, age = {}, None
    try:
        report = read_json(path)
        age = max(0.0, time.time() - path.stat().st_mtime)
    except (OSError, ValueError):
        report = {}
    lines = [
        "# HELP ba_drift_report_available 1 si un rapport de dérive est disponible.",
        "# TYPE ba_drift_report_available gauge",
        f"ba_drift_report_available {1 if report else 0}",
    ]
    if not report:
        return lines
    status = DRIFT_LEVELS.get(str(report.get("status")), -1)
    lines += [
        "# HELP ba_drift_status Dérive des données : 0 stable, 1 à surveiller, 2 dérive (-1 inconnu).",
        "# TYPE ba_drift_status gauge",
        f"ba_drift_status {status}",
        "# HELP ba_drift_psi_max PSI le plus élevé parmi les caractéristiques.",
        "# TYPE ba_drift_psi_max gauge",
        f"ba_drift_psi_max {report.get('max_psi', 0)}",
        "# HELP ba_drift_feature_psi PSI par caractéristique.",
        "# TYPE ba_drift_feature_psi gauge",
    ]
    for name, item in sorted((report.get("features") or {}).items()):
        lines.append(f'ba_drift_feature_psi{{feature="{name}"}} {item.get("psi", 0)}')
    lines += [
        "# HELP ba_drift_report_simulated 1 si le rapport vient de données volontairement décalées.",
        "# TYPE ba_drift_report_simulated gauge",
        f"ba_drift_report_simulated {1 if report.get('simulated') else 0}",
        "# HELP ba_drift_report_age_seconds Âge du rapport de dérive.",
        "# TYPE ba_drift_report_age_seconds gauge",
        f"ba_drift_report_age_seconds {age:.0f}",
    ]
    return lines


class RecommendationService:
    """Moteur de recommandation + compteurs de service (thread-safe)."""

    def __init__(self, rows):
        self.rows = rows
        self.started_at = time.time()
        self._engine_lock = threading.Lock()  # le moteur annote les lignes
        self._stats_lock = threading.Lock()
        self._by_status = {}
        self._latency_sum = 0.0
        self._latency_count = 0

    # --- prédiction -------------------------------------------------------
    def recommend(self, user_id, max_products=DEFAULT_MAX_PRODUCTS):
        try:
            with self._engine_lock:
                result = engine.build_recommendation(
                    user_id, max_products=max_products, feature_rows=self.rows
                )
        except ValueError as error:
            raise UnknownUser(user_id) from error
        result["model_version"] = engine.ACTIVE_MODEL_VERSION
        return result

    # --- informations -----------------------------------------------------
    def health(self):
        meta = read_json(AI_REPORT_PATH)
        return {
            "status": "ok",
            "model_version": engine.ACTIVE_MODEL_VERSION,
            "dataset_version": meta.get("dataset_version"),
            "users": len({row["user_id"] for row in self.rows}),
            "products": len({row["product_id"] for row in self.rows}),
        }

    def model_info(self):
        model = read_json(engine.MODEL_FILE)
        return {
            "version": engine.ACTIVE_MODEL_VERSION,
            "weights": dict(engine.SCORE_WEIGHTS),
            "origin": model.get("origin", "poids par défaut du moteur"),
            "created_at": model.get("created_at"),
            "training_data": model.get("data"),
            "metrics": model.get("metrics"),
        }

    # --- métriques --------------------------------------------------------
    def record(self, status, seconds):
        with self._stats_lock:
            self._by_status[status] = self._by_status.get(status, 0) + 1
            self._latency_sum += seconds
            self._latency_count += 1

    def prometheus_text(self):
        """Métriques au format texte Prometheus."""
        with self._stats_lock:
            by_status = dict(self._by_status)
            latency_sum, latency_count = self._latency_sum, self._latency_count
        info = self.model_info()
        lines = [
            "# HELP ba_requests_total Requêtes HTTP traitées, par code de statut.",
            "# TYPE ba_requests_total counter",
        ]
        for status, count in sorted(by_status.items()):
            lines.append(f'ba_requests_total{{code="{status}"}} {count}')
        lines += [
            "# HELP ba_request_duration_seconds Durée de traitement des requêtes.",
            "# TYPE ba_request_duration_seconds summary",
            f"ba_request_duration_seconds_sum {latency_sum:.6f}",
            f"ba_request_duration_seconds_count {latency_count}",
            "# HELP ba_model_info Version du modèle servi (valeur toujours 1).",
            "# TYPE ba_model_info gauge",
            f'ba_model_info{{version="{info["version"]}"}} 1',
            "# HELP ba_uptime_seconds Durée de fonctionnement du service.",
            "# TYPE ba_uptime_seconds gauge",
            f"ba_uptime_seconds {time.time() - self.started_at:.1f}",
        ]
        auc = (info.get("metrics") or {}).get("content_auc_test")
        if auc is not None:
            lines += [
                "# HELP ba_model_content_auc_test AUC de contenu du modèle servi sur le jeu de test.",
                "# TYPE ba_model_content_auc_test gauge",
                f"ba_model_content_auc_test {auc}",
            ]
        lines += drift_metric_lines()
        return "\n".join(lines) + "\n"
