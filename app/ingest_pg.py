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

USER_COLUMNS = [
    "user_id", "skin_type", "complexion", "undertone",
    "preferred_finish", "preferred_style", "max_budget", "created_at",
]

PRODUCT_COLUMNS = [
    "product_id", "brand", "name", "category", "price",
    "shade", "finish", "suitable_skin_type", "available", "updated_at",
]


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
                    f"Impossible de se connecter à PostgreSQL après {max_attempts} tentatives."
                ) from error

            print(f"PostgreSQL indisponible, nouvelle tentative {attempt}/{max_attempts}...")
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
    brands = ["Rare Beauty", "Fenty Beauty", "NYX", "Sephora Collection"]
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


def build_interactions(users, products, interactions_per_user: int = 8):
    """
    CORRECTION : le produit tiré n'est plus 100% aléatoire. ~75% des
    interactions par utilisateur portent sur un produit compatible avec
    son profil (type de peau ou fini préféré, dans son budget), le reste
    reste aléatoire pour simuler du bruit réaliste. Sans ça, aucun
    signal appris n'était disponible pour le moteur de recommandation.
    """
    user_dicts = [dict(zip(USER_COLUMNS, row)) for row in users]
    product_dicts = [dict(zip(PRODUCT_COLUMNS, row)) for row in products]

    interaction_types = ["favorite", "purchase", "review"]
    interactions = []
    interaction_index = 1

    for user in user_dicts:
        compatible = [
            p for p in product_dicts
            if (
                p["suitable_skin_type"] == user["skin_type"]
                or p["finish"] == user["preferred_finish"]
            )
            and p["price"] <= user["max_budget"] * 1.15
        ]
        incompatible = [p for p in product_dicts if p not in compatible]

        used_products = set()
        attempts = 0

        while (
            len(used_products) < interactions_per_user
            and attempts < interactions_per_user * 5
        ):
            attempts += 1

            use_compatible = rng.random() < 0.75 and compatible
            pool = compatible if use_compatible else (incompatible or product_dicts)
            product = rng.choice(pool)

            if product["product_id"] in used_products:
                continue

            used_products.add(product["product_id"])

            is_match = product in compatible

            if is_match:
                interaction_type = rng.choices(interaction_types, weights=[0.35, 0.35, 0.30])[0]
                rating = (
                    rng.choices([5, 4, 3], weights=[0.5, 0.35, 0.15])[0]
                    if interaction_type == "review" else None
                )
            else:
                interaction_type = rng.choices(interaction_types, weights=[0.15, 0.15, 0.70])[0]
                rating = (
                    rng.choices([1, 2, 3, 4], weights=[0.3, 0.3, 0.25, 0.15])[0]
                    if interaction_type == "review" else None
                )

            interactions.append(
                (
                    f"interaction_{interaction_index:04d}",
                    user["user_id"],
                    product["product_id"],
                    interaction_type,
                    rating,
                    datetime.now(timezone.utc),
                )
            )

            interaction_index += 1

    return interactions


def insert_rows(cursor, query: str, rows: list[tuple]) -> None:
    execute_values(cursor, query, rows, page_size=BATCH_SIZE)


def main() -> None:
    connection = None
    start_time = time.perf_counter()

    try:
        connection = connect_with_retry()
        print("✅ Connecté à PostgreSQL")

        with connection.cursor() as cursor:
            users = build_users()
            products = build_products()
            interactions = build_interactions(users, products)

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
            f"✅ Données PostgreSQL insérées : {len(users)} utilisateurs, "
            f"{len(products)} produits, {len(interactions)} interactions "
            f"en {duration} secondes."
        )

    except Exception:
        if connection is not None:
            connection.rollback()
        print("❌ Échec de l'ingestion PostgreSQL.")
        raise

    finally:
        if connection is not None:
            connection.close()
            print("✅ Connexion PostgreSQL fermée.")


if __name__ == "__main__":
    main()