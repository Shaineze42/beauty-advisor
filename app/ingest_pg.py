import os
import random
import time
from datetime import datetime, timezone

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

load_dotenv()

rng = random.Random(42)
BATCH_SIZE = 1000


def get_env(name: str, default: str) -> str:
    return os.getenv(name, default)


def connect_with_retry(max_attempts: int = 10, delay_seconds: int = 3):
    connection_params = {
        "host": get_env("POSTGRES_HOST", "postgres"),
        "port": int(get_env("POSTGRES_PORT", "5432")),
        "dbname": get_env("POSTGRES_DB", "beauty_advisor"),
        "user": get_env("POSTGRES_USER", "beauty_user"),
        "password": get_env("POSTGRES_PASSWORD", "change_me"),
    }

    for attempt in range(1, max_attempts + 1):
        try:
            return psycopg2.connect(**connection_params)

        except psycopg2.OperationalError as error:
            if attempt == max_attempts:
                raise RuntimeError(
                    "Impossible de se connecter à PostgreSQL après "
                    f"{max_attempts} tentatives."
                ) from error

            print(
                f"PostgreSQL indisponible, nouvelle tentative "
                f"{attempt}/{max_attempts}..."
            )
            time.sleep(delay_seconds)

    raise RuntimeError("Connexion PostgreSQL impossible.")


def build_users(count: int = 20):
    skin_types = ["sèche", "grasse", "mixte", "normale"]
    complexions = ["claire", "medium", "foncée"]
    undertones = ["chaud", "froid", "neutre"]
    finishes = ["mat", "naturel", "glowy"]
    styles = ["naturel", "sophistiqué", "quotidien"]

    now = datetime.now(timezone.utc)

    return [
        (
            f"user_{index:03d}",
            rng.choice(skin_types),
            rng.choice(complexions),
            rng.choice(undertones),
            rng.choice(finishes),
            rng.choice(styles),
            float(rng.choice([30, 50, 60, 80, 100])),
            now,
        )
        for index in range(1, count + 1)
    ]


def build_products(count: int = 50):
    brands = [
        "Rare Beauty",
        "Fenty Beauty",
        "NYX",
        "Sephora Collection",
    ]

    categories = ["teint", "blush", "yeux", "lèvres"]
    finishes = ["mat", "naturel", "glowy"]
    skin_types = ["sèche", "grasse", "mixte", "normale"]
    shades = ["rose", "nude", "bronze", "marron", "rouge"]

    now = datetime.now(timezone.utc)
    products = []

    for index in range(1, count + 1):
        category = rng.choice(categories)
        brand = rng.choice(brands)

        products.append(
            (
                f"prod_{index:03d}",
                brand,
                f"{category.title()} {brand} {index:03d}",
                category,
                round(rng.uniform(8, 65), 2),
                rng.choice(shades),
                rng.choice(finishes),
                rng.choice(skin_types),
                True,
                now,
            )
        )

    return products


def build_interactions(user_count: int = 20, product_count: int = 50):
    interaction_types = ["favorite", "purchase", "review"]
    interactions = []
    interaction_index = 1

    for user_index in range(1, user_count + 1):
        for _ in range(5):
            interaction_type = rng.choice(interaction_types)

            rating = (
                rng.randint(1, 5)
                if interaction_type == "review"
                else None
            )

            interactions.append(
                (
                    f"interaction_{interaction_index:04d}",
                    f"user_{user_index:03d}",
                    f"prod_{rng.randint(1, product_count):03d}",
                    interaction_type,
                    rating,
                    datetime.now(timezone.utc),
                )
            )

            interaction_index += 1

    return interactions


def insert_rows(cursor, query: str, rows: list[tuple]) -> None:
    execute_values(
        cursor,
        query,
        rows,
        page_size=BATCH_SIZE,
    )


def main() -> None:
    connection = None
    start_time = time.perf_counter()

    try:
        connection = connect_with_retry()
        print("✅ Connecté à PostgreSQL")

        with connection.cursor() as cursor:
            users = build_users()
            products = build_products()
            interactions = build_interactions()

            insert_rows(
                cursor,
                (
                    "INSERT INTO users ("
                    "user_id, skin_type, complexion, undertone, "
                    "preferred_finish, preferred_style, max_budget, created_at) "
                    "VALUES %s ON CONFLICT (user_id) DO NOTHING"
                ),
                users,
            )

            insert_rows(
                cursor,
                (
                    "INSERT INTO products ("
                    "product_id, brand, name, category, price, shade, "
                    "finish, suitable_skin_type, available, updated_at) "
                    "VALUES %s ON CONFLICT (product_id) DO NOTHING"
                ),
                products,
            )

            insert_rows(
                cursor,
                (
                    "INSERT INTO interactions ("
                    "interaction_id, user_id, product_id, "
                    "interaction_type, rating, created_at) "
                    "VALUES %s ON CONFLICT (interaction_id) DO NOTHING"
                ),
                interactions,
            )

        connection.commit()

        duration = round(time.perf_counter() - start_time, 2)

        print(
            f"✅ Données PostgreSQL insérées : "
            f"{len(users)} utilisateurs, "
            f"{len(products)} produits, "
            f"{len(interactions)} interactions "
            f"en {duration} secondes."
        )

    except Exception:
        if connection is not None:
            connection.rollback()

        print("❌ Échec de l’ingestion PostgreSQL.")
        raise

    finally:
        if connection is not None:
            connection.close()
            print("✅ Connexion PostgreSQL fermée.")


if __name__ == "__main__":
    main()