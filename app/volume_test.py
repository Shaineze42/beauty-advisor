import os
import random
import time

import psycopg2
import psutil
from dotenv import load_dotenv
from psycopg2.extras import execute_values

load_dotenv()

BATCH_SIZE = 1000
rng = random.Random(42)
process = psutil.Process(os.getpid())


def get_env(name: str, default: str) -> str:
    return os.getenv(name, default)


def connect_to_postgres():
    return psycopg2.connect(
        host=get_env("POSTGRES_HOST", "postgres"),
        port=int(get_env("POSTGRES_PORT", "5432")),
        dbname=get_env("POSTGRES_DB", "beauty_advisor"),
        user=get_env("POSTGRES_USER", "beauty_user"),
        password=get_env("POSTGRES_PASSWORD", "change_me"),
    )


def get_test_sizes() -> list[int]:
    raw_sizes = get_env(
        "VOLUME_TEST_SIZES",
        "1000,10000,100000",
    )

    sizes = [
        int(value.strip())
        for value in raw_sizes.split(",")
    ]

    if any(size <= 0 for size in sizes):
        raise ValueError(
            "Les volumes de test doivent être positifs."
        )

    return sizes


def create_temp_table(cursor) -> None:
    query = (
        "CREATE TEMP TABLE IF NOT EXISTS "
        "volume_test_products ("
        "product_id VARCHAR(50) PRIMARY KEY, "
        "brand VARCHAR(100) NOT NULL, "
        "name VARCHAR(150) NOT NULL, "
        "category VARCHAR(50) NOT NULL, "
        "price NUMERIC(10, 2) NOT NULL, "
        "available BOOLEAN NOT NULL) "
        "ON COMMIT PRESERVE ROWS"
    )

    cursor.execute(query)


def build_batch(start_index: int, end_index: int):
    brands = [
        "Rare Beauty",
        "Fenty Beauty",
        "NYX",
        "Sephora Collection",
    ]

    categories = [
        "teint",
        "blush",
        "yeux",
        "lèvres",
    ]

    return [
        (
            f"volume_{index:08d}",
            brands[index % len(brands)],
            f"Produit de test {index}",
            categories[index % len(categories)],
            round(8 + rng.random() * 57, 2),
            True,
        )
        for index in range(start_index, end_index)
    ]


def insert_volume(cursor, volume: int) -> None:
    query = (
        "INSERT INTO volume_test_products ("
        "product_id, brand, name, category, price, available) "
        "VALUES %s "
        "ON CONFLICT (product_id) DO NOTHING"
    )

    for start_index in range(1, volume + 1, BATCH_SIZE):
        end_index = min(
            start_index + BATCH_SIZE,
            volume + 1,
        )

        batch = build_batch(
            start_index,
            end_index,
        )

        execute_values(
            cursor,
            query,
            batch,
            page_size=BATCH_SIZE,
        )


def run_volume_tests(connection) -> None:
    sizes = get_test_sizes()
    results = []

    with connection.cursor() as cursor:
        create_temp_table(cursor)
        connection.commit()

        for volume in sizes:
            cursor.execute(
                "TRUNCATE volume_test_products"
            )
            connection.commit()

            memory_before = (
                process.memory_info().rss
                / (1024 * 1024)
            )

            start_time = time.perf_counter()

            insert_volume(cursor, volume)
            connection.commit()

            duration = round(
                time.perf_counter() - start_time,
                2,
            )

            memory_after = (
                process.memory_info().rss
                / (1024 * 1024)
            )

            cursor.execute(
                "SELECT COUNT(*) "
                "FROM volume_test_products"
            )

            inserted_count = cursor.fetchone()[0]

            results.append(
                (
                    volume,
                    inserted_count,
                    duration,
                    round(
                        memory_after - memory_before,
                        2,
                    ),
                )
            )

        cursor.execute(
            "TRUNCATE volume_test_products"
        )
        connection.commit()

        insert_volume(cursor, 1000)
        connection.commit()

        insert_volume(cursor, 1000)
        connection.commit()

        cursor.execute(
            "SELECT COUNT(*) "
            "FROM volume_test_products"
        )

        idempotent_count = cursor.fetchone()[0]

    print("\n" + "=" * 65)
    print("RÉSULTATS DES TESTS DE VOLUMÉTRIE")
    print("=" * 65)
    print(
        "Volume      Lignes      Temps (s)      "
        "Mémoire supplémentaire (MB)"
    )
    print("-" * 65)

    for volume, count, duration, memory_delta in results:
        print(
            f"{volume:>6}      "
            f"{count:>6}      "
            f"{duration:>8}      "
            f"{memory_delta:>12}"
        )

    print("-" * 65)

    if idempotent_count == 1000:
        print(
            "✅ Idempotence validée : "
            "aucun doublon créé."
        )
    else:
        raise RuntimeError(
            "❌ Échec de l'idempotence : "
            "le nombre de lignes est incorrect."
        )


def main() -> None:
    connection = None

    try:
        connection = connect_to_postgres()

        print(
            "✅ Connecté à PostgreSQL "
            "pour les tests de volumétrie."
        )

        run_volume_tests(connection)

    except Exception:
        if connection is not None:
            connection.rollback()

        print("❌ Échec du test de volumétrie.")
        raise

    finally:
        if connection is not None:
            connection.close()
            print("✅ Connexion PostgreSQL fermée.")


if __name__ == "__main__":
    main()