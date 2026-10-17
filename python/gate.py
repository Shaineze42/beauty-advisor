"""Portail qualité, transformation SQL et clôture d'un run."""
from __future__ import annotations

import json

import quality
from db import SQL_DIR, connect, run_sql_file


def transform() -> None:
    """Étape T de l'ELT : agrégats analytiques en SQL."""
    run_sql_file("20_aggregate.sql")


def quality_gate(run_id: str) -> list[dict]:
    """Mesure, évalue et enregistre les contrôles. Retourne la liste des contrôles."""
    statements = [s for s in (SQL_DIR / "30_quality_checks.sql").read_text(encoding="utf-8").split(";") if "SELECT" in s]
    with connect() as conn, conn.cursor() as cur:
        cur.execute(statements[0])
        freshness = cur.fetchone()[0]
        cur.execute(statements[1])
        violations = cur.fetchone()[0]
        cur.execute("SELECT consumed, rejected, lag FROM pipeline.runs WHERE run_id = %s", (run_id,))
        consumed, rejected, lag = cur.fetchone()
        checks = quality.evaluate_checks({
            "consumed": consumed, "rejected": rejected, "lag": lag,
            "freshness_seconds": freshness, "integrity_violations": violations})
        for c in checks:
            cur.execute("""
                INSERT INTO pipeline.quality_checks (run_id, check_name, value, threshold, passed)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (run_id, check_name) DO UPDATE
                SET value = EXCLUDED.value, threshold = EXCLUDED.threshold,
                    passed = EXCLUDED.passed, checked_at = now()""",
                (run_id, c["name"], c["value"], c["threshold"], c["passed"]))
    print(json.dumps(checks, ensure_ascii=False))
    return checks


def finalize(run_id: str, failed: bool) -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE pipeline.runs SET finished_at = now(), status = %s WHERE run_id = %s""",
            ("failed" if failed else "success", run_id))
        if cur.rowcount == 0:  # échec avant l'ingestion : on garde une trace du run
            cur.execute("""
                INSERT INTO pipeline.runs (run_id, finished_at, status) VALUES (%s, now(), 'failed')""", (run_id,))
