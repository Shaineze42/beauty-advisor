from pathlib import Path

import pytest

from api.service import RecommendationService, UnknownUser, engine

ROOT = Path(__file__).resolve().parents[2]
HAS_DATA = (ROOT / "data/processed/ai_features.csv").exists()
needs_data = pytest.mark.skipif(not HAS_DATA, reason="données non préparées")


@pytest.fixture
def service():
    return RecommendationService(engine.read_features())


@needs_data
def test_recommendation_respects_the_requested_size(service):
    result = service.recommend("user_001", 3)
    assert result["status"] == "success"
    assert 1 <= len(result["routine"]) <= 3
    assert result["model_version"] == engine.ACTIVE_MODEL_VERSION


@needs_data
def test_unknown_user_raises(service):
    with pytest.raises(UnknownUser):
        service.recommend("user_inexistant", 4)


@needs_data
def test_health_and_model_info(service):
    health = service.health()
    assert health["status"] == "ok" and health["users"] > 0 and health["products"] > 0
    info = service.model_info()
    assert abs(sum(info["weights"].values()) - 1.0) < 1e-6
    assert info["version"] == engine.ACTIVE_MODEL_VERSION


@needs_data
def test_prometheus_text_counts_requests(service):
    service.record(200, 0.010)
    service.record(200, 0.030)
    service.record(404, 0.005)
    text = service.prometheus_text()
    assert 'ba_requests_total{code="200"} 2' in text
    assert 'ba_requests_total{code="404"} 1' in text
    assert "ba_request_duration_seconds_count 3" in text
    assert 'ba_model_info{version="' in text
