import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient
from pymongo.errors import PyMongoError

load_dotenv()


def get_env(name: str, default: str) -> str:
    return os.getenv(name, default)


def main() -> None:
    client = None

    try:
        client = MongoClient(
            host=get_env("MONGO_HOST", "mongodb"),
            port=int(get_env("MONGO_PORT", "27017")),
            username=get_env("MONGO_ROOT_USER", "admin"),
            password=get_env("MONGO_ROOT_PASSWORD", "change_me"),
            authSource="admin",
            serverSelectionTimeoutMS=10000,
        )

        client.admin.command("ping")
        print("✅ Connecté à MongoDB")

        database = client[get_env("MONGO_DB", "beauty_advisor")]

        requests_collection = database[
            "recommendation_requests"
        ]

        routines_collection = database["routines"]

        requests_collection.create_index(
            [("request_id", ASCENDING)],
            unique=True,
        )

        routines_collection.create_index(
            [("routine_id", ASCENDING)],
            unique=True,
        )

        routines_collection.create_index(
            [("user_id", ASCENDING)]
        )

        now = datetime.now(timezone.utc)

        request_documents = []
        routine_documents = []

        for index in range(1, 11):
            request_id = f"request_{index:03d}"
            routine_id = f"routine_{index:03d}"
            user_id = f"user_{index:03d}"

            request_documents.append(
                {
                    "request_id": request_id,
                    "user_id": user_id,
                    "context": {
                        "occasion": (
                            "mariage"
                            if index % 2 == 0
                            else "quotidien"
                        ),
                        "style": (
                            "naturel"
                            if index % 2 == 0
                            else "sophistiqué"
                        ),
                        "finish": (
                            "glowy"
                            if index % 2 == 0
                            else "naturel"
                        ),
                        "budget": 60,
                        "preferred_colors": [
                            "rose",
                            "bronze",
                        ],
                    },
                    "status": "processed",
                    "created_at": now,
                }
            )

            routine_documents.append(
                {
                    "routine_id": routine_id,
                    "request_id": request_id,
                    "user_id": user_id,
                    "products": [
                        {
                            "product_id": f"prod_{index:03d}",
                            "category": "teint",
                            "score": 0.92,
                            "reason": (
                                "Correspond au profil utilisateur."
                            ),
                        },
                        {
                            "product_id": f"prod_{index + 10:03d}",
                            "category": "blush",
                            "score": 0.87,
                            "reason": (
                                "Correspond aux préférences "
                                "déclarées."
                            ),
                        },
                    ],
                    "total_price": 54.90,
                    "model_version": "v1",
                    "created_at": now,
                }
            )

        for document in request_documents:
            requests_collection.update_one(
                {"request_id": document["request_id"]},
                {"$set": document},
                upsert=True,
            )

        for document in routine_documents:
            routines_collection.update_one(
                {"routine_id": document["routine_id"]},
                {"$set": document},
                upsert=True,
            )

        print(
            f"✅ MongoDB alimenté : "
            f"{len(request_documents)} demandes et "
            f"{len(routine_documents)} routines."
        )

    except PyMongoError:
        print("❌ Échec de l’ingestion MongoDB.")
        raise

    finally:
        if client is not None:
            client.close()
            print("✅ Connexion MongoDB fermée.")


if __name__ == "__main__":
    main()