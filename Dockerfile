# Image de serving : API FastAPI + modèle actif + données préparées.
# Construction en deux étapes : la préparation des données (pandas, etc.) reste
# dans la première étape ; l'image finale ne contient que FastAPI et le moteur.

FROM python:3.11-slim AS data
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /build
COPY app/requirements.txt app/requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt
COPY app app
COPY data/raw data/raw
RUN python app/validate_data.py \
    && python app/transform_data.py \
    && python app/prepare_ai_data.py

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BA_MODEL_FILE=/srv/models/current.json
WORKDIR /srv
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt \
    && useradd --system --uid 10001 --no-create-home ba
COPY app app
COPY api api
COPY models models
COPY --from=data /build/data/processed data/processed
COPY --from=data /build/reports reports
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
