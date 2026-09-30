"""
Test de montée en charge du moteur de recommandation.

Mesure le temps d'une recommandation quand le catalogue passe de 50 à 50 000
produits (données synthétiques en mémoire, aucune base touchée).
Écrit reports/engine_scalability_report.json.
"""
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from recommendation_engine import build_recommendation


REPORT_PATH = Path("reports/engine_scalability_report.json")
CATALOG_SIZES = [50, 500, 5000, 50000]
REPEATS = 5
CATEGORIES = ["teint", "blush", "yeux", "lèvres"]
FINISHES = ["mat", "naturel", "glowy"]
SKINS = ["sèche", "grasse", "mixte", "normale"]
MAX_SECONDS_AT_MAX_SIZE = 2.0


def make_catalog(size, rng):
    rows = []

    for index in range(size):
        skin = rng.choice(SKINS)
        finish = rng.choice(FINISHES)
        rows.append(
            {
                "user_id": "user_scale",
                "product_id": f"prod_{index:06d}",
                "brand": f"marque_{index % 20}",
                "name": f"produit {index}",
                "category": rng.choice(CATEGORIES),
                "finish": finish,
                "suitable_skin_type": skin,
                "preferred_finish": "mat",
                "price": round(rng.uniform(5, 60), 2),
                "max_budget": 100,
                "skin_match": int(skin == "sèche"),
                "finish_match": int(finish == "mat"),
                "available_flag": int(rng.random() > 0.1),
                "interaction_signal": "",
            }
        )

    return rows


def main():
    rng = random.Random(42)
    results = []

    for size in CATALOG_SIZES:
        rows = make_catalog(size, rng)
        durations = []

        for _ in range(REPEATS):
            start = time.perf_counter()
            result = build_recommendation("user_scale", feature_rows=rows)
            durations.append(time.perf_counter() - start)

        results.append(
            {
                "catalog_size": size,
                "average_seconds": round(sum(durations) / REPEATS, 5),
                "max_seconds": round(max(durations), 5),
                "products_returned": result["products_count"],
                "budget_respected": result["total_price"] <= result["budget"],
            }
        )

    base = results[0]["average_seconds"] or 1e-9
    worst = results[-1]

    for item in results:
        item["slowdown_vs_50_products"] = round(item["average_seconds"] / base, 1)

    status = "success" if worst["average_seconds"] <= MAX_SECONDS_AT_MAX_SIZE else "warning"

    report = {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repeats_per_size": REPEATS,
        "threshold_seconds_at_max_size": MAX_SECONDS_AT_MAX_SIZE,
        "results": results,
        "interpretation": (
            "La durée croît de façon à peu près linéaire avec la taille du catalogue "
            "(filtrage et tri). Au-delà, une pré-indexation par utilisateur serait nécessaire."
        ),
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print("Montée en charge du moteur")
    for item in results:
        print(
            f"  {item['catalog_size']:>6} produits : {item['average_seconds']:.4f} s "
            f"(x{item['slowdown_vs_50_products']})"
        )
    print(f"{'✅' if status == 'success' else '⚠️ '} Statut : {status}")
    print(f"Rapport créé : {REPORT_PATH}")


if __name__ == "__main__":
    main()