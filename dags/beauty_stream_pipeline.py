"""DAG Airflow : pipeline d'interactions en quasi temps réel (micro-lots toutes les 2 minutes).

    init_schema -> ingest_batch -> transform_sql -> quality_gate -> finalize_run

- ingest_batch  : lit le flux Kafka, applique validation/correction, charge en base, met en quarantaine ;
- transform_sql : agrégats analytiques en SQL (ELT) ;
- quality_gate  : contrôles de qualité ; fait échouer le run si un seuil est franchi ;
- finalize_run  : enregistre le statut du run (toujours exécuté) puis propage l'échec éventuel.

Gestion d'erreurs : 2 nouvelles tentatives par tâche (délai 20 s) ; l'ingestion est idempotente
(upsert + offsets validés après commit), donc un rejeu ne duplique rien.
"""
from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.exceptions import AirflowFailException
from airflow.operators.python import PythonOperator
from airflow.utils.trigger_rule import TriggerRule

DEFAULT_ARGS = {
    "owner": "beauty-advisor",
    "retries": 2,
    "retry_delay": timedelta(seconds=20),
    "execution_timeout": timedelta(minutes=5),
}


def _init_schema():
    from db import ensure_schema
    ensure_schema()


def _ingest(run_id, **_):
    from consumer import ingest_batch
    return ingest_batch(run_id)


def _transform():
    from gate import transform
    transform()


def _quality(run_id, **_):
    from gate import quality_gate
    checks = quality_gate(run_id)
    failed = [c["name"] for c in checks if not c["passed"]]
    if failed:
        # AirflowFailException : pas de nouvelle tentative, la donnée est le problème
        raise AirflowFailException(f"Contrôles qualité en échec : {', '.join(failed)}")


def _finalize(run_id, dag_run, **_):
    from gate import finalize
    failed_tasks = [ti.task_id for ti in dag_run.get_task_instances()
                    if ti.task_id != "finalize_run" and ti.state in ("failed", "upstream_failed")]
    finalize(run_id, failed=bool(failed_tasks))
    if failed_tasks:
        raise AirflowFailException(f"Run en échec : {', '.join(failed_tasks)}")


with DAG(
    dag_id="beauty_stream_pipeline",
    description="Flux d'interactions : ingestion, qualité, transformation SQL, contrôles",
    default_args=DEFAULT_ARGS,
    schedule="*/2 * * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    tags=["beauty-advisor", "streaming"],
) as dag:
    init_schema = PythonOperator(task_id="init_schema", python_callable=_init_schema)
    ingest = PythonOperator(task_id="ingest_batch", python_callable=_ingest, op_kwargs={"run_id": "{{ run_id }}"})
    transform = PythonOperator(task_id="transform_sql", python_callable=_transform)
    quality_gate = PythonOperator(task_id="quality_gate", python_callable=_quality, op_kwargs={"run_id": "{{ run_id }}"})
    finalize = PythonOperator(task_id="finalize_run", python_callable=_finalize,
                              op_kwargs={"run_id": "{{ run_id }}"}, trigger_rule=TriggerRule.ALL_DONE)

    init_schema >> ingest >> transform >> quality_gate >> finalize
