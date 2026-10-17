"""Ingestion par micro-lots depuis le flux Kafka (Redpanda).

Garanties :
  - lecture sans validation automatique des offsets ;
  - chargement en base dans UNE transaction ;
  - offsets validés seulement APRÈS le commit (au moins une fois) ;
  - upsert sur interaction_id (ON CONFLICT DO NOTHING) : rejouer un lot ne duplique rien.
"""
from __future__ import annotations

import json
import os
import time
from datetime import timezone

from psycopg2.extras import execute_values

import quality
from db import connect, ensure_schema

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "redpanda:9092")
TOPIC = os.environ.get("KAFKA_TOPIC", "interactions.raw")
GROUP = os.environ.get("KAFKA_GROUP", "beauty-ingest")


def _naive_utc(dt):
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def read_batch(max_messages: int, max_seconds: float):
    """Lit les messages disponibles au moment de l'appel, puis s'arrête (micro-lot).

    On fixe les fins de partitions dès que le groupe a ses partitions, puis on lit jusqu'à
    les atteindre (ou jusqu'à max_messages / max_seconds). Le producteur continue d'écrire :
    ces nouveaux messages seront traités par le run suivant, ce qui borne la durée d'un run.
    Retourne (consumer, messages)."""
    from kafka import KafkaConsumer

    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=BOOTSTRAP,
        group_id=GROUP,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        max_poll_records=1000,
        request_timeout_ms=30000,
    )
    messages = []
    ends = None
    empty_polls = 0
    deadline = time.monotonic() + max_seconds
    while len(messages) < max_messages and time.monotonic() < deadline:
        batches = consumer.poll(timeout_ms=2000)
        for records in batches.values():
            messages.extend(records)
        parts = list(consumer.assignment())
        if ends is None and parts:
            ends = consumer.end_offsets(parts)
        if ends is not None and all(consumer.position(p) >= ends[p] for p in parts):
            break  # rattrapé : tout ce qui existait au départ est lu
        if not batches:
            empty_polls += 1
            if empty_polls >= 5:
                break
        else:
            empty_polls = 0
    return consumer, messages


def ingest_batch(run_id: str, max_messages: int = 25000, max_seconds: float = 90.0) -> dict:
    ensure_schema()
    consumer, messages = read_batch(max_messages, max_seconds)
    try:
        payloads = [m.value for m in messages]
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM public.users")
                users = {r[0] for r in cur.fetchall()}
                cur.execute("SELECT product_id FROM public.products")
                products = {r[0] for r in cur.fetchall()}

                result = quality.process_batch(payloads, users, products)
                kept = {item["index"]: item for item in result["loaded"]}
                quarantined = {item["index"]: item["reason"] for item in result["quarantine"]}

                raw_rows, quarantine_rows, interaction_rows = [], [], []
                for idx, msg in enumerate(messages):
                    text = msg.value.decode("utf-8", errors="replace")
                    if idx in quarantined:
                        raw_rows.append((msg.topic, msg.partition, msg.offset, None, "rejected", quarantined[idx], text))
                        quarantine_rows.append((msg.topic, msg.partition, msg.offset, quarantined[idx], text))
                    elif idx in kept:
                        ev = kept[idx]["event"]
                        raw_rows.append((msg.topic, msg.partition, msg.offset, ev["event_id"], kept[idx]["status"],
                                         ",".join(kept[idx]["corrections"]) or None, text))
                        interaction_rows.append((ev["event_id"], ev["user_id"], ev["product_id"],
                                                 ev["interaction_type"], ev["rating"], _naive_utc(ev["created_at"])))
                    else:
                        raw_rows.append((msg.topic, msg.partition, msg.offset, None, "duplicate", None, text))

                inserted = 0
                for i in range(0, len(interaction_rows), 1000):
                    chunk = interaction_rows[i:i + 1000]
                    # RETURNING + fetch : execute_values envoie par paquets, rowcount ne verrait que le dernier
                    rows = execute_values(cur, """
                        INSERT INTO public.interactions
                            (interaction_id, user_id, product_id, interaction_type, rating, created_at)
                        VALUES %s ON CONFLICT (interaction_id) DO NOTHING
                        RETURNING interaction_id""", chunk, fetch=True)
                    inserted += len(rows)
                if raw_rows:
                    execute_values(cur, """
                        INSERT INTO pipeline.raw_events
                            (topic, partition_id, "offset", event_id, status, corrections, payload)
                        VALUES %s ON CONFLICT DO NOTHING""", raw_rows, page_size=1000)
                if quarantine_rows:
                    execute_values(cur, """
                        INSERT INTO pipeline.quarantine (topic, partition_id, "offset", reason, payload)
                        VALUES %s ON CONFLICT DO NOTHING""", quarantine_rows, page_size=1000)

                # Retard restant du consommateur (positions + fin de partitions)
                parts = consumer.assignment()
                ends = consumer.end_offsets(list(parts)) if parts else {}
                lag = sum(max(ends[p] - consumer.position(p), 0) for p in parts)

                stats = result["stats"]
                stats["duplicates"] += len(interaction_rows) - inserted  # doublons déjà en base
                cur.execute("""
                    INSERT INTO pipeline.runs (run_id, consumed, loaded, corrected, rejected, duplicates, lag)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id) DO UPDATE SET
                        consumed = EXCLUDED.consumed, loaded = EXCLUDED.loaded, corrected = EXCLUDED.corrected,
                        rejected = EXCLUDED.rejected, duplicates = EXCLUDED.duplicates, lag = EXCLUDED.lag,
                        status = 'running', finished_at = NULL""",
                    (run_id, len(messages), inserted, stats["corrected"], stats["rejected"],
                     stats["duplicates"], lag))
            conn.commit()
        consumer.commit()  # offsets validés seulement après le commit en base
    finally:
        consumer.close()

    summary = {"consumed": len(messages), "loaded": inserted, "corrected": stats["corrected"],
               "rejected": stats["rejected"], "duplicates": stats["duplicates"], "lag": lag,
               "rejection_reasons": result["reasons"]}
    print(json.dumps(summary, ensure_ascii=False))
    return summary
