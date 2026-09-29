import os
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

load_dotenv()

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
PROCESSED_DIR = DATA_DIR / "processed"
BATCH_SIZE = 1000


def get_env(name: str, default: str) -> str:
    return os.getenv(name, default)


def connect_to_postgres():
    return psycopg2.connect(
        host=get_env("POSTGRES_HOST", "postgres"),
        port=int(get_env("POSTGRES_PORT", "5432")),
        dbname=get_env("POSTGRES_DB", "beauty_advisor"),
        user=get_env("POSTGRES_USER", "beauty_user"),
        password=get_env(
            "POSTGRES_PASSWORD",
            "change_me",
        ),
    )


def python_value(value):
    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        return value.item()

    return value


def load_users(cursor) -> int:
    dataframe = pd.read_csv(
        PROCESSED_DIR / "users_raw.csv"
    )

    rows = [
        (
            row.user_id,
            row.skin_type,
            row.complexion,
            row.undertone,
            row.preferred_finish,
            row.preferred_style,
            python_value(row.max_budget),
            row.created_at,
        )
        for row in dataframe.itertuples(
            index=False
        )
    ]

    query = (
        "INSERT INTO users ("
        "user_id, skin_type, complexion, undertone, "
        "preferred_finish, preferred_style, "
        "max_budget, created_at) "
        "VALUES %s "
        "ON CONFLICT (user_id) DO UPDATE SET "
        "skin_type = EXCLUDED.skin_type, "
        "complexion = EXCLUDED.complexion, "
        "undertone = EXCLUDED.undertone, "
        "preferred_finish = EXCLUDED.preferred_finish, "
        "preferred_style = EXCLUDED.preferred_style, "
        "max_budget = EXCLUDED.max_budget"
    )

    execute_values(
        cursor,
        query,
        rows,
        page_size=BATCH_SIZE,
    )

    return len(rows)


def load_products(cursor) -> int:
    dataframe = pd.read_csv(
        PROCESSED_DIR / "products_raw.csv"
    )

    rows = [
        (
            row.product_id,
            row.brand,
            row.name,
            row.category,
            python_value(row.price),
            python_value(row.shade),
            row.finish,
            row.suitable_skin_type,
            bool(row.available),
            row.updated_at,
        )
        for row in dataframe.itertuples(
            index=False
        )
    ]

    query = (
        "INSERT INTO products ("
        "product_id, brand, name, category, price, "
        "shade, finish, suitable_skin_type, "
        "available, updated_at) "
        "VALUES %s "
        "ON CONFLICT (product_id) DO UPDATE SET "
        "brand = EXCLUDED.brand, "
        "name = EXCLUDED.name, "
        "category = EXCLUDED.category, "
        "price = EXCLUDED.price, "
        "shade = EXCLUDED.shade, "
        "finish = EXCLUDED.finish, "
        "suitable_skin_type = EXCLUDED.suitable_skin_type, "
        "available = EXCLUDED.available, "
        "updated_at = EXCLUDED.updated_at"
    )

    execute_values(
        cursor,
        query,
        rows,
        page_size=BATCH_SIZE,
    )

    return len(rows)


def load_interactions(cursor) -> int:
    dataframe = pd.read_csv(
        PROCESSED_DIR / "interactions_raw.csv"
    )

    rows = [
        (
            row.interaction_id,
            row.user_id,
            row.product_id,
            row.interaction_type,
            python_value(row.rating),
            row.created_at,
        )
        for row in dataframe.itertuples(
            index=False
        )
    ]

    query = (
        "INSERT INTO interactions ("
        "interaction_id, user_id, product_id, "
        "interaction_type, rating, created_at) "
        "VALUES %s "
        "ON CONFLICT (interaction_id) DO UPDATE SET "
        "user_id = EXCLUDED.user_id, "
        "product_id = EXCLUDED.product_id, "
        "interaction_type = EXCLUDED.interaction_type, "
        "rating = EXCLUDED.rating"
    )

    execute_values(
        cursor,
        query,
        rows,
        page_size=BATCH_SIZE,
    )

    return len(rows)


def main() -> None:
    connection = None

    try:
        connection = connect_to_postgres()

        with connection.cursor() as cursor:
            users_count = load_users(cursor)
            products_count = load_products(cursor)
            interactions_count = load_interactions(
                cursor
            )

        connection.commit()

        print("✅ Chargement PostgreSQL terminé")
        print(
            f"Utilisateurs chargés : {users_count}"
        )
        print(
            f"Produits chargés : {products_count}"
        )
        print(
            f"Interactions chargées : "
            f"{interactions_count}"
        )

    except Exception:
        if connection is not None:
            connection.rollback()

        print("❌ Échec du chargement PostgreSQL")
        raise

    finally:
        if connection is not None:
            connection.close()
            print("✅ Connexion PostgreSQL fermée")


if __name__ == "__main__":
    main()