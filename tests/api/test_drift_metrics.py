"""Métriques de dérive exposées par l'API (lues dans le rapport de monitoring/drift.py)."""
import json
import os
from pathlib import Path

import pytest

from api.service import RecommendationService, drift_metric_lines, engine

ROOT = Path(__file__).resolve().parents[2]
HAS_DATA = (ROOT / "data/processed/ai_features.csv").exists()
needs_data = pytest.mark.skipif(not HAS_DATA, reason="données non préparées")

REPORT = {
    "status": "drift",
    "max_psi": 4.2291,
    "features": {
        "skin_match": {"psi": 0.0005, "status": "stable"},
        "budget_score": {"psi": 4.2291, "status": "drift"},
    },
    "simulated": True,
}


def _write(tmp_path, report):
    path = tmp_path / "drift_report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def test_sans_rapport_seule_la_disponibilite_est_exposee(tmp_path):
    text = "\n".join(drift_metric_lines(tmp_path / "absent.json"))
    assert "ba_drift_report_available 0" in text
    assert "ba_drift_status" not in text


def test_rapport_illisible_ne_fait_pas_planter(tmp_path):
    path = tmp_path / "drift_report.json"
    path.write_text("{pas du json", encoding="utf-8")
    assert "ba_drift_report_available 0" in "\n".join(drift_metric_lines(path))


def test_rapport_de_derive_est_expose(tmp_path):
    text = "\n".join(drift_metric_lines(_write(tmp_path, REPORT)))
    assert "ba_drift_report_available 1" in text
    assert "ba_drift_status 2" in text
    assert "ba_drift_psi_max 4.2291" in text
    assert 'ba_drift_feature_psi{feature="budget_score"} 4.2291' in text
    assert "ba_drift_report_simulated 1" in text
    assert "ba_drift_report_age_seconds" in text


def test_statuts_stable_et_warning(tmp_path):
    stable = dict(REPORT, status="stable", simulated=False)
    warning = dict(REPORT, status="warning")
    assert "ba_drift_status 0" in "\n".join(drift_metric_lines(_write(tmp_path, stable)))
    assert "ba_drift_status 1" in "\n".join(drift_metric_lines(_write(tmp_path, warning)))


def test_statut_inconnu_vaut_moins_un(tmp_path):
    text = "\n".join(drift_metric_lines(_write(tmp_path, dict(REPORT, status="???"))))
    assert "ba_drift_status -1" in text


@needs_data
def test_metrics_de_l_api_contiennent_la_derive(tmp_path):
    service = RecommendationService(engine.read_features())
    path = _write(tmp_path, REPORT)
    old = os.environ.get("BA_DRIFT_REPORT")
    os.environ["BA_DRIFT_REPORT"] = str(path)
    try:
        text = service.prometheus_text()
    finally:
        if old is None:
            os.environ.pop("BA_DRIFT_REPORT", None)
        else:
            os.environ["BA_DRIFT_REPORT"] = old
    assert "ba_drift_status 2" in text
    assert "ba_uptime_seconds" in text
