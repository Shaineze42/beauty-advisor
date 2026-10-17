import json
import random
from datetime import datetime, timedelta, timezone

import quality

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
USERS, PRODUCTS = {"user_001", "user_002"}, {"prod_001", "prod_002"}


def ev(**over):
    base = {"event_id": "evt-1", "user_id": "user_001", "product_id": "prod_001",
            "interaction_type": "purchase", "rating": 4, "ts": NOW.isoformat()}
    base.update(over)
    return base


def run(payload):
    return quality.validate_and_correct(json.dumps(payload) if not isinstance(payload, (str, bytes)) else payload, NOW)


def test_evenement_valide():
    r = run(ev())
    assert r["status"] == "valid" and r["corrections"] == []
    assert r["event"]["rating"] == 4


def test_type_corrige_casse_et_espaces():
    r = run(ev(interaction_type=" PURCHASE "))
    assert r["status"] == "corrected"
    assert r["event"]["interaction_type"] == "purchase"
    assert "type_mis_en_minuscules" in r["corrections"]


def test_type_francais_traduit():
    r = run(ev(interaction_type="achat"))
    assert r["status"] == "corrected" and r["event"]["interaction_type"] == "purchase"


def test_note_texte_convertie():
    r = run(ev(interaction_type="review", rating="5"))
    assert r["status"] == "corrected" and r["event"]["rating"] == 5


def test_date_invalide_remplacee_par_date_ingestion():
    r = run(ev(ts="hier soir"))
    assert r["status"] == "corrected" and r["event"]["created_at"] == NOW


def test_rejets():
    assert run(ev(interaction_type="wishlist"))["reason"] == "type_inconnu"
    assert run(ev(rating=9))["reason"] == "note_hors_plage"
    assert run(ev(rating="beaucoup"))["reason"] == "note_invalide"
    assert run(ev(rating=3.5))["reason"] == "note_invalide"
    assert run(ev(ts=(NOW + timedelta(days=2)).isoformat()))["reason"] == "date_future"
    assert run('{"event_id": "x", "user_id":')["reason"] == "json_invalide"
    assert run("[1, 2]")["reason"] == "json_invalide"
    broken = ev(); broken.pop("user_id")
    assert run(broken)["reason"] == "champ_manquant:user_id"
    assert run(ev(product_id="  "))["reason"] == "champ_manquant:product_id"


def test_note_absente_acceptee():
    r = run(ev(interaction_type="favorite", rating=None))
    assert r["status"] == "valid" and r["event"]["rating"] is None


def test_references():
    assert quality.check_references(ev(), USERS, PRODUCTS) is None
    assert quality.check_references(ev(user_id="user_999"), USERS, PRODUCTS) == "utilisateur_inconnu"
    assert quality.check_references(ev(product_id="prod_999"), USERS, PRODUCTS) == "produit_inconnu"


def test_lot_complet_doublons_et_quarantaine():
    payloads = [
        json.dumps(ev(event_id="a")),
        json.dumps(ev(event_id="a")),                       # doublon dans le lot
        json.dumps(ev(event_id="b", interaction_type="ACHAT")),
        json.dumps(ev(event_id="c", user_id="user_999")),   # référence inconnue
        b"{casse",
    ]
    res = quality.process_batch(payloads, USERS, PRODUCTS, NOW)
    assert res["stats"] == {"valid": 1, "corrected": 1, "rejected": 2, "duplicates": 1}
    assert res["reasons"] == {"utilisateur_inconnu": 1, "json_invalide": 1}
    assert [i["index"] for i in res["loaded"]] == [0, 2]


def test_tous_les_statuts_somment_au_total():
    rng = random.Random(7)
    import producer
    prev = []
    msgs = [producer.make_message(rng, ["user_001", "user_002"], ["prod_001", "prod_002"], NOW, 0.5, prev)[0]
            for _ in range(500)]
    res = quality.process_batch(msgs, USERS, PRODUCTS, NOW)
    s = res["stats"]
    assert sum(s.values()) == 500
    assert s["rejected"] > 0 and s["corrected"] > 0
