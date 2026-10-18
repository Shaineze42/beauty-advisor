import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HAS_DATA = (ROOT / "data/processed/train.csv").exists() and (
    ROOT / "data/processed/ai_features.csv"
).exists()


def run_retrain(tmp_path, *extra):
    command = [
        sys.executable, "retrain/retrain.py",
        "--models-dir", str(tmp_path / "models"),
        "--report", str(tmp_path / "report.json"),
        *extra,
    ]
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True)


@pytest.mark.skipif(not HAS_DATA, reason="données non préparées (python app/prepare_ai_data.py)")
def test_first_run_creates_baseline_then_second_run_does_nothing(tmp_path):
    first = run_retrain(tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr
    registry = json.loads((tmp_path / "models/registry.json").read_text(encoding="utf-8"))
    assert registry["active"] == "v0"
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert "pas de modèle actif" in report["triggers"]
    assert "promote" in report["decision"]

    second = run_retrain(tmp_path)
    assert second.returncode == 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["triggers"] == []


@pytest.mark.skipif(not HAS_DATA, reason="données non préparées (python app/prepare_ai_data.py)")
def test_simulated_drift_triggers_retraining_and_dry_run_writes_no_model(tmp_path):
    run_retrain(tmp_path)
    before = sorted(p.name for p in (tmp_path / "models/versions").iterdir())
    result = run_retrain(tmp_path, "--simulate-drift", "--dry-run")
    assert result.returncode == 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert "dérive des données" in report["triggers"]
    assert report["dry_run"] is True
    assert sorted(p.name for p in (tmp_path / "models/versions").iterdir()) == before
