"""API de serving Beauty Advisor (FastAPI).

Lancement depuis la racine du dépôt, après la préparation des données :
  uvicorn api.main:app --port 8000
Documentation interactive : http://localhost:8000/docs

Endpoints :
  GET  /health      état du service et version du modèle
  GET  /model       modèle servi : version, poids, métriques d'entraînement
  POST /recommend   routine personnalisée pour un utilisateur
  GET  /metrics     métriques au format Prometheus

Variable d'environnement API_KEY : si elle est définie, POST /recommend exige
l'en-tête X-API-Key correspondant.
"""
import hmac
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from api.service import (
    DEFAULT_MAX_PRODUCTS,
    MAX_PRODUCTS_LIMIT,
    USER_ID_PATTERN,
    RecommendationService,
    UnknownUser,
    engine,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("beauty_api")


@asynccontextmanager
async def lifespan(app):
    app.state.service = RecommendationService(engine.read_features())
    logger.info("Service prêt : modèle %s, %s lignes",
                engine.ACTIVE_MODEL_VERSION, len(app.state.service.rows))
    yield


app = FastAPI(
    title="Beauty Advisor API",
    version="1.0.0",
    description="Recommandation de routines makeup personnalisées et explicables.",
    lifespan=lifespan,
)


class RecommendRequest(BaseModel):
    user_id: str = Field(
        pattern=USER_ID_PATTERN,
        description="Identifiant de l'utilisateur (lettres, chiffres, _ et -).",
        examples=["user_001"],
    )
    max_products: int = Field(
        default=DEFAULT_MAX_PRODUCTS,
        ge=1,
        le=MAX_PRODUCTS_LIMIT,
        description="Nombre maximal de produits dans la routine.",
    )


def require_key(x_api_key: Optional[str] = Header(default=None)):
    expected = os.getenv("API_KEY")
    if expected and not hmac.compare_digest(x_api_key or "", expected):
        raise HTTPException(status_code=401, detail="Clé API absente ou invalide.")


def get_service(request: Request):
    return request.app.state.service


@app.middleware("http")
async def observe(request: Request, call_next):
    """Identifiant de requête, durée, journal et compteurs de service."""
    start = time.perf_counter()
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Erreur non gérée [%s]", request_id)
        response = JSONResponse({"detail": "Erreur interne."}, status_code=500)
    seconds = time.perf_counter() - start
    response.headers["X-Request-ID"] = request_id
    service = getattr(request.app.state, "service", None)
    if service is not None:
        service.record(response.status_code, seconds)
    logger.info("%s %s -> %s (%.1f ms) [%s]", request.method, request.url.path,
                response.status_code, seconds * 1000, request_id)
    return response


@app.get("/health", summary="État du service")
def health(request: Request):
    return get_service(request).health()


@app.get("/model", summary="Modèle actuellement servi")
def model(request: Request):
    return get_service(request).model_info()


@app.post("/recommend", summary="Routine personnalisée", dependencies=[Depends(require_key)])
def recommend(payload: RecommendRequest, request: Request):
    try:
        return get_service(request).recommend(payload.user_id, payload.max_products)
    except UnknownUser:
        raise HTTPException(status_code=404, detail="Utilisateur inconnu.")
    except Exception:
        logger.exception("Erreur interne pendant la recommandation")
        raise HTTPException(status_code=500, detail="Erreur interne.")


@app.get("/metrics", summary="Métriques Prometheus", response_class=PlainTextResponse)
def metrics(request: Request):
    return PlainTextResponse(
        get_service(request).prometheus_text(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
