import json

import pytest

import recommendation_engine as engine


@pytest.fixture(autouse=True)
def restore_default_weights(tmp_path):
    yield
    engine.load_active_weights(tmp_path / "absent.json")


def write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


GOOD = {
    "skin_match": 0.30, "finish_match": 0.20, "budget_score": 0.15,
    "availability": 0.10, "interaction": 0.15, "history_match": 0.10,
}


def test_missing_file_keeps_default_weights(tmp_path):
    version = engine.load_active_weights(tmp_path / "absent.json")
    assert version == "v0-defaut"
    assert engine.SCORE_WEIGHTS == engine.DEFAULT_SCORE_WEIGHTS


def test_valid_model_is_applied(tmp_path):
    path = write(tmp_path / "current.json", {"version": "v7", "weights": GOOD})
    assert engine.load_active_weights(path) == "v7"
    assert engine.SCORE_WEIGHTS["skin_match"] == 0.30


def test_weights_not_summing_to_one_are_refused(tmp_path):
    bad = dict(GOOD, skin_match=0.50)
    path = write(tmp_path / "current.json", {"version": "v8", "weights": bad})
    assert engine.load_active_weights(path) == "v0-defaut"
    assert engine.SCORE_WEIGHTS == engine.DEFAULT_SCORE_WEIGHTS


def test_missing_key_is_refused(tmp_path):
    bad = {k: v for k, v in GOOD.items() if k != "history_match"}
    path = write(tmp_path / "current.json", {"version": "v9", "weights": bad})
    assert engine.load_active_weights(path) == "v0-defaut"


def test_corrupted_file_does_not_crash_the_service(tmp_path):
    path = tmp_path / "current.json"
    path.write_text("{ pas du json", encoding="utf-8")
    assert engine.load_active_weights(path) == "v0-defaut"
