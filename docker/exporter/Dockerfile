FROM python:3.11-slim

WORKDIR /exporter

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY exporter.py .

EXPOSE 9100

CMD ["python", "exporter.py"]
