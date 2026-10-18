from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
HAS_DATA = (ROOT / "data/processed/ai_features.csv").exists()
needs_data = pytest.mark.skipif(not HAS_DATA, reason="données non préparées")


@pytest.fixture
def client():
    from api.main import app

    with TestClient(app) as test_client:
        yield test_client


@needs_data
def test_health_returns_ok_and_model_version(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "model_version" in response.json()
    assert response.headers["x-request-id"]


@needs_data
def test_recommend_returns_a_routine(client):
    response = client.post("/recommend", json={"user_id": "user_001", "max_products": 4})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert 1 <= len(body["routine"]) <= 4
    assert all(product["reasons"] for product in body["routine"])


@needs_data
def test_unknown_user_gives_404(client):
    response = client.post("/recommend", json={"user_id": "user_inexistant"})
    assert response.status_code == 404


@needs_data
def test_invalid_input_gives_422(client):
    assert client.post("/recommend", json={"user_id": "bad id!"}).status_code == 422
    assert client.post("/recommend", json={"user_id": "user_001", "max_products": 99}).status_code == 422
    assert client.post("/recommend", json={}).status_code == 422


@needs_data
def test_get_on_recommend_is_not_allowed(client):
    assert client.get("/recommend").status_code == 405


@needs_data
def test_api_key_is_enforced_when_configured(client, monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-de-test")
    body = {"user_id": "user_001"}
    assert client.post("/recommend", json=body).status_code == 401
    assert client.post("/recommend", json=body, headers={"X-API-Key": "faux"}).status_code == 401
    assert client.post("/recommend", json=body, headers={"X-API-Key": "secret-de-test"}).status_code == 200


@needs_data
def test_model_and_metrics_endpoints(client):
    client.get("/health")
    model = client.get("/model").json()
    assert abs(sum(model["weights"].values()) - 1.0) < 1e-6
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "ba_requests_total" in metrics.text
