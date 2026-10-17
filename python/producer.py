"""Producteur d'événements d'interaction (flux continu, données synthétiques).

Publie en continu des événements JSON dans le topic Kafka. Une part contrôlée d'événements
est volontairement dégradée pour que les contrôles qualité aient quelque chose à détecter :
  - corrigeables : casse/espaces, type en français, note en texte, date invalide ;
  - rejetables   : champ manquant, type inconnu, note hors plage, produit ou utilisateur
                   inconnu, JSON cassé, date future ;
  - doublons     : ré-émission d'un événement déjà envoyé.
"""
from __future__ import annotations

import json
import os
import random
import signal
import time
import uuid
from datetime import datetime, timedelta, timezone



BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "redpanda:9092")
TOPIC = os.environ.get("KAFKA_TOPIC", "interactions.raw")

DIRTY_KINDS = [
    "type_majuscules", "type_francais", "note_texte", "date_invalide",
    "user_manquant", "type_inconnu", "note_hors_plage", "produit_inconnu",
    "utilisateur_inconnu", "json_casse", "date_future", "doublon",
]


def clean_event(rng: random.Random, users: list[str], products: list[str], now: datetime) -> dict:
    itype = rng.choices(["favorite", "purchase", "review"], weights=[4, 3, 3])[0]
    rating = rng.randint(1, 5) if itype == "review" or rng.random() < 0.4 else None
    return {
        "event_id": f"evt-{uuid.UUID(int=rng.getrandbits(128)).hex[:16]}",
        "user_id": rng.choice(users),
        "product_id": rng.choice(products),
        "interaction_type": itype,
        "rating": rating,
        "ts": now.isoformat(),
    }


def make_message(rng: random.Random, users: list[str], products: list[str], now: datetime,
                 dirty_ratio: float, previous: list[dict]) -> tuple[bytes, str]:
    """Retourne (message, nature) ; nature = 'propre' ou le type de dégradation."""
    ev = clean_event(rng, users, products, now)
    if rng.random() >= dirty_ratio:
        previous.append(ev)
        del previous[:-50]
        return json.dumps(ev).encode(), "propre"
    kind = rng.choice(DIRTY_KINDS)
    if kind == "type_majuscules":
        ev["interaction_type"] = f" {ev['interaction_type'].upper()} "
    elif kind == "type_francais":
        ev["interaction_type"] = {"favorite": "favori", "purchase": "achat", "review": "avis"}[ev["interaction_type"]]
    elif kind == "note_texte":
        ev["interaction_type"], ev["rating"] = "review", str(rng.randint(1, 5))
    elif kind == "date_invalide":
        ev["ts"] = "hier soir"
    elif kind == "user_manquant":
        ev.pop("user_id")
    elif kind == "type_inconnu":
        ev["interaction_type"] = "wishlist"
    elif kind == "note_hors_plage":
        ev["interaction_type"], ev["rating"] = "review", rng.choice([0, 6, 9, -1])
    elif kind == "produit_inconnu":
        ev["product_id"] = "prod_999"
    elif kind == "utilisateur_inconnu":
        ev["user_id"] = "user_999"
    elif kind == "json_casse":
        return b'{"event_id": "evt-broken", "user_id":', kind
    elif kind == "date_future":
        ev["ts"] = (now + timedelta(days=2)).isoformat()
    elif kind == "doublon" and previous:
        return json.dumps(rng.choice(previous)).encode(), kind
    return json.dumps(ev).encode(), kind


def main() -> None:
    from kafka import KafkaAdminClient, KafkaProducer
    from kafka.admin import NewTopic
    from kafka.errors import TopicAlreadyExistsError

    rate = float(os.environ.get("STREAM_RATE", "5"))            # événements par seconde
    dirty_ratio = float(os.environ.get("DIRTY_RATIO", "0.10"))
    max_events = int(os.environ.get("MAX_EVENTS", "0"))          # 0 = flux sans fin
    rng = random.Random(int(os.environ["SEED"])) if os.environ.get("SEED") else random.Random()

    import db

    db.ensure_schema()
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT user_id FROM public.users")
        users = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT product_id FROM public.products")
        products = [r[0] for r in cur.fetchall()]
    if not users or not products:
        raise SystemExit("Aucun utilisateur ou produit en base : chargez d'abord le jeu de référence.")

    admin = KafkaAdminClient(bootstrap_servers=BOOTSTRAP)
    try:
        admin.create_topics([NewTopic(TOPIC, num_partitions=3, replication_factor=1)])
    except TopicAlreadyExistsError:
        pass
    admin.close()

    producer = KafkaProducer(bootstrap_servers=BOOTSTRAP, key_serializer=str.encode, linger_ms=20)
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))

    previous: list[dict] = []
    sent = 0
    started = time.monotonic()
    print(f"Producteur démarré : {rate} événements/s, {dirty_ratio:.0%} dégradés, topic {TOPIC}", flush=True)
    while not stop["flag"] and not (max_events and sent >= max_events):
        tick = time.monotonic()
        batch = max(1, int(rate)) if rate >= 1 else 1
        for _ in range(batch):
            msg, _kind = make_message(rng, users, products, datetime.now(timezone.utc), dirty_ratio, previous)
            producer.send(TOPIC, key=rng.choice(users), value=msg)
            sent += 1
        producer.flush()
        if sent % 500 < batch:
            print(f"{sent} événements publiés en {time.monotonic() - started:.0f} s", flush=True)
        time.sleep(max(0.0, (batch / rate) - (time.monotonic() - tick)))
    producer.flush()
    producer.close()


if __name__ == "__main__":
    main()
