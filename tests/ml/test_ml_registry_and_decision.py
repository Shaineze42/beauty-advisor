import json

import pytest

from beauty_ml import registry
from beauty_ml.evaluation import CRITICAL_RULES, decide


def model(version, w=0.25):
    weights = {
        "skin_match": w, "finish_match": 0.20, "budget_score": 0.20,
        "availability": 0.10, "interaction": 0.15, "history_match": round(0.10 + 0.25 - w, 4),
    }
    return {"version": version, "weights": weights}


def metrics(auc, precision=0.5, broken=None):
    critical = {name: 1.0 for name in CRITICAL_RULES}
    if broken:
        critical[broken] = 0.9
    return {"content_auc_test": auc, "precision_functional": precision, "critical": critical}


# --- registre -------------------------------------------------------------

def test_versions_are_numbered_from_zero(tmp_path):
    assert registry.next_version(tmp_path) == "v0"
    registry.save_version(model("v0"), tmp_path)
    assert registry.next_version(tmp_path) == "v1"


def test_promotion_copies_the_model_to_current(tmp_path):
    registry.save_version(model("v0"), tmp_path)
    registry.promote("v0", tmp_path)
    assert registry.load_active(tmp_path)["version"] == "v0"
    assert registry.load_registry(tmp_path)["active"] == "v0"


def test_unknown_version_cannot_be_promoted(tmp_path):
    with pytest.raises(FileNotFoundError):
        registry.promote("v9", tmp_path)


def test_rollback_returns_to_the_previous_promoted_version(tmp_path):
    for version in ("v0", "v1"):
        registry.save_version(model(version), tmp_path)
        registry.record(tmp_path, version, "promu", "test", {})
        registry.promote(version, tmp_path)
    assert registry.rollback(tmp_path) == "v0"
    assert registry.load_active(tmp_path)["version"] == "v0"


def test_rollback_ignores_rejected_versions(tmp_path):
    registry.save_version(model("v0"), tmp_path)
    registry.record(tmp_path, "v0", "promu", "test", {})
    registry.promote("v0", tmp_path)
    registry.save_version(model("v1"), tmp_path)
    registry.record(tmp_path, "v1", "rejeté", "test", {})
    with pytest.raises(ValueError):
        registry.rollback(tmp_path)


# --- décision de promotion --------------------------------------------------

def test_candidate_with_enough_gain_is_promoted():
    result = decide(metrics(0.70), metrics(0.65))
    assert result["promote"] is True


def test_insufficient_gain_is_refused():
    result = decide(metrics(0.652), metrics(0.65))
    assert result["promote"] is False
    assert "gain" in result["reason"]


def test_business_rule_violation_blocks_promotion_even_with_better_auc():
    result = decide(metrics(0.90, broken="budget_compliance"), metrics(0.65))
    assert result["promote"] is False
    assert "budget_compliance" in result["reason"]


def test_precision_drop_blocks_promotion():
    result = decide(metrics(0.80, precision=0.40), metrics(0.65, precision=0.50))
    assert result["promote"] is False
    assert "précision" in result["reason"]
