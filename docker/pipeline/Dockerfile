FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/python
RUN pip install --no-cache-dir kafka-python==2.0.2 psycopg2-binary==2.9.9 \
    && useradd --uid 10001 --no-create-home pipeline
WORKDIR /app
USER pipeline

CMD ["python", "/app/python/producer.py"]
