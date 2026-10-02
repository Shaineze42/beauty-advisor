"""
Enregistre dans MongoDB (collection `routines`) les routines générées par
le moteur de recommandation de Beauty Advisor.

Pourquoi MongoDB : une routine est un document de forme variable (nombre de
produits, explications de longueur variable, replis éventuels), sans
jointure nécessaire. Le lien avec PostgreSQL passe par `user_id`
(jointure applicative).

Principes :
  - idempotent : un `routine_id` déterministe + upsert, relancer le script
    ne crée jamais de doublon ;
  - le budget de la demande (`context.budget` dans la collection
    `recommendation_requests`) est prioritaire sur le budget du profil ;
    sans demande, on utilise le budget du profil. Le champ `budget_source`
    indique l'origine du budget utilisé ;
  - aucune donnée personnelle ajoutée : uniquement l'identifiant technique.

Usage (dans le conteneur app) :
    python save_routines_mongo.py
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

MODEL_VERSION = "scoring-hybride-v1"
COLLECTION_NAME = "routines"
REQUESTS_COLLECTION_NAME = "recommendation_requests"


def routine_id_for(user_id):
    """Identifiant déterministe : une routine courante par utilisatrice."""
    return f"routine_{user_id}"


def request_budget_of(request):
    """
    Extrait le budget d'une demande. Dans MongoDB, le budget est dans le
    sous-document `context` ; on accepte aussi un champ `budget` à plat.
    Retourne None si la demande n'a pas de budget exploitable.
    """
    if not request:
        return None

    context = request.get("context") or {}
    budget = context.get("budget", request.get("budget"))

    try:
        value = float(budget)
    except (TypeError, ValueError):
        return None

    return value if value > 0 else None


def rows_with_request_budget(rows, user_id, request_budget):
    """
    Retourne une copie des lignes de l'utilisatrice dont le budget est celui
    de la demande. Les lignes des autres utilisatrices ne sont pas modifiées
    et les lignes d'origine ne sont jamais altérées.
    """
    if request_budget is None:
        return rows

    adjusted = []
    for row in rows:
        if row.get("user_id") == user_id:
            copy = dict(row)
            copy["max_budget"] = str(request_budget)
            adjusted.append(copy)
        else:
            adjusted.append(row)
    return adjusted


def build_routine_document(
    result, request_id=None, created_at=None, budget_source="profile"
):
    """
    Transforme le résultat du moteur en document MongoDB.
    Ne contient que des identifiants techniques et des données produit.
    """
    created_at = created_at or datetime.now(timezone.utc)

    return {
        "routine_id": routine_id_for(result["user_id"]),
        "request_id": request_id,
        "user_id": result["user_id"],
        "status": result["status"],
        "budget": result["budget"],
        "budget_source": budget_source,
        "total_price": result["total_price"],
        "products_count": result["products_count"],
        "products": [
            {
                "product_id": item["product_id"],
                "category": item["category"],
                "price": item["price"],
                "score": item["score"],
                "reasons": item["reasons"],
            }
            for item in result["routine"]
        ],
        "fallbacks": result.get("fallbacks", {}),
        "model_version": MODEL_VERSION,
        "created_at": created_at,
    }


def main():
    from dotenv import load_dotenv
    from pymongo import ASCENDING, MongoClient

    from recommendation_engine import build_recommendation, read_features

    load_dotenv()

    client = MongoClient(
        host=os.getenv("MONGO_HOST", "mongodb"),
        port=int(os.getenv("MONGO_PORT", "27017")),
        username=os.getenv("MONGO_ROOT_USER", "admin"),
        password=os.getenv("MONGO_ROOT_PASSWORD", "change_me"),
        authSource="admin",
        serverSelectionTimeoutMS=10000,
    )

    try:
        client.admin.command("ping")
        database = client[os.getenv("MONGO_DB", "beauty_advisor")]

        routines = database[COLLECTION_NAME]
        routines.create_index([("routine_id", ASCENDING)], unique=True)
        routines.create_index([("user_id", ASCENDING)])

        requests_by_user = {}
        for request in database[REQUESTS_COLLECTION_NAME].find({}):
            requests_by_user[request["user_id"]] = request

        rows = read_features()
        user_ids = sorted({row["user_id"] for row in rows})

        saved = 0
        with_request = 0
        with_request_budget = 0

        for user_id in user_ids:
            request = requests_by_user.get(user_id)
            budget = request_budget_of(request)

            user_rows = rows_with_request_budget(rows, user_id, budget)
            result = build_recommendation(user_id, feature_rows=user_rows)

            document = build_routine_document(
                result,
                request_id=request.get("request_id") if request else None,
                budget_source="request" if budget is not None else "profile",
            )

            routines.update_one(
                {"routine_id": document["routine_id"]},
                {"$set": document},
                upsert=True,
            )

            saved += 1
            with_request += 1 if request else 0
            with_request_budget += 1 if budget is not None else 0

        print("✅ Enregistrement des routines terminé")
        print(f"Routines enregistrées : {saved}")
        print(f"dont avec une demande : {with_request}")
        print(f"dont avec le budget de la demande : {with_request_budget}")
        print(f"Total dans la collection : {routines.count_documents({})}")

    finally:
        client.close()


if __name__ == "__main__":
    if not Path("data/processed/ai_features.csv").exists():
        print(
            "❌ data/processed/ai_features.csv introuvable : "
            "lancez d'abord prepare_ai_data.py (ou run_bloc4.py)."
        )
        sys.exit(1)
    main()