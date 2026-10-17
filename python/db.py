"""Connexion PostgreSQL et création idempotente du schéma du pipeline."""
import os
from pathlib import Path

import psycopg2

SQL_DIR = Path(os.environ.get("SQL_DIR", Path(__file__).resolve().parent.parent / "sql"))


def connect():
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "postgres"),
        port=int(os.environ.get("POSTGRES_PORT_INTERNAL", "5432")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        connect_timeout=10,
    )


def run_sql_file(name: str) -> None:
    """Exécute un fichier de /sql dans une transaction."""
    sql = (SQL_DIR / name).read_text(encoding="utf-8")
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)


def ensure_schema() -> None:
    run_sql_file("00_schema.sql")
