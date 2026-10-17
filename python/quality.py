"""Règles de qualité et de correction des événements d'interaction.

Fonctions pures (sans accès réseau ni base) : elles sont testées unitairement.

Chaque événement reçoit un statut :
  - valid     : conforme tel quel ;
  - corrected : conforme après correction automatique (liste des corrections conservée) ;
  - rejected  : non corrigeable, envoyé en quarantaine avec sa raison.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

VALID_TYPES = {"favorite", "purchase", "review"}
TYPE_SYNONYMS = {"achat": "purchase", "favori": "favorite", "avis": "review"}
MAX_FUTURE = timedelta(minutes=5)
REQUIRED = ("event_id", "user_id", "product_id", "interaction_type")


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def validate_and_correct(payload: str | bytes, now: datetime | None = None) -> dict:
    """Valide un message brut. Retourne {status, event, corrections, reason}."""
    now = now or datetime.now(timezone.utc)
    corrections: list[str] = []

    def rejected(reason: str) -> dict:
        return {"status": "rejected", "event": None, "corrections": corrections, "reason": reason}

    try:
        data = json.loads(payload)
    except (ValueError, TypeError):
        return rejected("json_invalide")
    if not isinstance(data, dict):
        return rejected("json_invalide")

    event: dict[str, Any] = {}
    for field in REQUIRED:
        value = data.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            return rejected(f"champ_manquant:{field}")
        if isinstance(value, str) and value != value.strip():
            corrections.append(f"espaces_retires:{field}")
        event[field] = str(value).strip()

    raw_type = event["interaction_type"]
    itype = raw_type.lower()
    if itype != raw_type:
        corrections.append("type_mis_en_minuscules")
    if itype in TYPE_SYNONYMS:
        itype = TYPE_SYNONYMS[itype]
        corrections.append("type_traduit")
    if itype not in VALID_TYPES:
        return rejected("type_inconnu")
    event["interaction_type"] = itype

    rating = data.get("rating")
    if rating is not None and rating != "":
        if isinstance(rating, bool):
            return rejected("note_invalide")
        if isinstance(rating, str):
            try:
                rating = float(rating.strip().replace(",", "."))
                corrections.append("note_convertie_en_nombre")
            except ValueError:
                return rejected("note_invalide")
        if not isinstance(rating, (int, float)) or (isinstance(rating, float) and not rating.is_integer()):
            return rejected("note_invalide")
        rating = int(rating)
        if not 1 <= rating <= 5:
            return rejected("note_hors_plage")
        event["rating"] = rating
    else:
        event["rating"] = None

    ts = _parse_ts(data.get("ts"))
    if ts is None:
        ts = now
        corrections.append("date_remplacee_par_date_ingestion")
    elif ts > now + MAX_FUTURE:
        return rejected("date_future")
    event["created_at"] = ts

    return {
        "status": "corrected" if corrections else "valid",
        "event": event,
        "corrections": corrections,
        "reason": None,
    }


def check_references(event: dict, users: set[str], products: set[str]) -> str | None:
    """Intégrité référentielle : retourne la raison de rejet ou None."""
    if event["user_id"] not in users:
        return "utilisateur_inconnu"
    if event["product_id"] not in products:
        return "produit_inconnu"
    return None


def process_batch(payloads: list[str | bytes], users: set[str], products: set[str],
                  now: datetime | None = None) -> dict:
    """Applique toutes les règles à un lot. Retourne les événements retenus et la quarantaine."""
    loaded: list[dict] = []
    quarantine: list[dict] = []
    seen: set[str] = set()
    stats = {"valid": 0, "corrected": 0, "rejected": 0, "duplicates": 0}
    reasons: dict[str, int] = {}
    for idx, raw in enumerate(payloads):
        res = validate_and_correct(raw, now)
        if res["status"] != "rejected":
            reason = check_references(res["event"], users, products)
            if reason:
                res = {"status": "rejected", "event": None, "corrections": [], "reason": reason}
        if res["status"] == "rejected":
            stats["rejected"] += 1
            reasons[res["reason"]] = reasons.get(res["reason"], 0) + 1
            quarantine.append({"index": idx, "reason": res["reason"]})
            continue
        if res["event"]["event_id"] in seen:
            stats["duplicates"] += 1
            continue
        seen.add(res["event"]["event_id"])
        stats[res["status"]] += 1
        loaded.append({"index": idx, **res})
    return {"loaded": loaded, "quarantine": quarantine, "stats": stats, "reasons": reasons}


# ---------- Portail qualité (appliqué après le chargement) ----------

DEFAULT_THRESHOLDS = {"max_rejection_rate": 0.30, "max_freshness_seconds": 600, "max_lag": 20000}


def evaluate_checks(metrics: dict, thresholds: dict | None = None) -> list[dict]:
    """Évalue les contrôles qualité d'un run. `metrics` : consumed, rejected, lag,
    freshness_seconds (None si aucune donnée), integrity_violations."""
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    consumed = metrics.get("consumed", 0)
    rate = (metrics.get("rejected", 0) / consumed) if consumed else 0.0
    fresh = metrics.get("freshness_seconds")
    checks = [
        ("taux_de_rejet", rate, th["max_rejection_rate"], rate <= th["max_rejection_rate"]),
        ("fraicheur_secondes", fresh if fresh is not None else -1.0, th["max_freshness_seconds"],
         fresh is not None and fresh <= th["max_freshness_seconds"]),
        ("retard_consommateur", metrics.get("lag", 0), th["max_lag"], metrics.get("lag", 0) <= th["max_lag"]),
        ("violations_integrite", metrics.get("integrity_violations", 0), 0, metrics.get("integrity_violations", 0) == 0),
    ]
    return [{"name": n, "value": float(v), "threshold": float(t), "passed": bool(p)} for n, v, t, p in checks]
