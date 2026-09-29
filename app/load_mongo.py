import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient
from pymongo.errors import PyMongoError

load_dotenv()

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
PROCESSED_DIR = DATA_DIR / "processed"


def get_env(name: str, default: str) -> str:
    return os.getenv(name, default)


def parse_datetime(value):
    if not value:
        return value

    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


def main() -> None:
    client = None

    try:
        client = MongoClient(
            host=get_env("MONGO_HOST", "mongodb"),
            port=int(get_env("MONGO_PORT", "27017")),
            username=get_env(
                "MONGO_ROOT_USER",
                "admin",
            ),
            password=get_env(
                "MONGO_ROOT_PASSWORD",
                "change_me",
            ),
            authSource="admin",
            serverSelectionTimeoutMS=10000,
        )

        client.admin.command("ping")

        database = client[
            get_env(
                "MONGO_DB",
                "beauty_advisor",
            )
        ]

        collection = database[
            "recommendation_requests"
        ]

        collection.create_index(
            [("request_id", ASCENDING)],
            unique=True,
        )

        source = (
            PROCESSED_DIR
            / "recommendation_requests.json"
        )

        with source.open(
            "r",
            encoding="utf-8",
        ) as file:
            documents = json.load(file)

        for document in documents:
            if "created_at" in document:
                document["created_at"] = parse_datetime(
                    document["created_at"]
                )

            collection.update_one(
                {
                    "request_id": document[
                        "request_id"
                    ]
                },
                {"$set": document},
                upsert=True,
            )

        print("✅ Chargement MongoDB terminé")
        print(
            f"Demandes chargées : {len(documents)}"
        )

    except PyMongoError:
        print("❌ Échec du chargement MongoDB")
        raise

    finally:
        if client is not None:
            client.close()
            print("✅ Connexion MongoDB fermée")


if __name__ == "__main__":
    main()