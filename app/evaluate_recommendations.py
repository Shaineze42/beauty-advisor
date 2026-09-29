import csv
import json
import time
from collections import defaultdict
from pathlib import Path

from recommendation_engine import build_recommendation


FEATURES_PATH = Path(
    "data/processed/ai_features.csv"
)
TEST_PATH = Path("data/processed/test.csv")
REPORT_PATH = Path(
    "reports/evaluation_report.json"
)

TOP_K = 4


def read_csv(path):
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:
        return list(csv.DictReader(file))


features = read_csv(FEATURES_PATH)
test_rows = read_csv(TEST_PATH)

relevant_products = defaultdict(set)

for row in test_rows:
    if row.get("label") == "1":
        relevant_products[
            row["user_id"]
        ].add(row["product_id"])

evaluated_users = sorted(relevant_products)
all_products = {
    row["product_id"]
    for row in features
}

results = []
errors = []
recommended_products = set()

for user_id in evaluated_users:
    start_time = time.perf_counter()

    try:
        recommendation = build_recommendation(
            user_id,
            max_products=TOP_K,
            use_interactions=False,
        )

        duration = time.perf_counter() - start_time

        recommended_ids = {
            product["product_id"]
            for product in recommendation["routine"]
        }

        relevant_ids = relevant_products[user_id]
        hits = recommended_ids.intersection(
            relevant_ids
        )

        precision = len(hits) / TOP_K
        recall = len(hits) / len(relevant_ids)
        hit_rate = int(len(hits) > 0)

        recommended_products.update(
            recommended_ids
        )

        budget = recommendation["budget"]
        total_price = recommendation["total_price"]
        budget_respected = (
            budget is None
            or total_price <= budget
        )

        results.append(
            {
                "user_id": user_id,
                "recommended_products": len(
                    recommended_ids
                ),
                "relevant_products": len(
                    relevant_ids
                ),
                "hits": len(hits),
                "precision_at_4": round(
                    precision,
                    4,
                ),
                "recall_at_4": round(
                    recall,
                    4,
                ),
                "hit_rate_at_4": hit_rate,
                "latency_seconds": round(
                    duration,
                    4,
                ),
                "budget_respected": (
                    budget_respected
                ),
            }
        )

    except Exception as error:
        errors.append(
            {
                "user_id": user_id,
                "error": str(error),
            }
        )


if results:
    precision_average = sum(
        result["precision_at_4"]
        for result in results
    ) / len(results)

    recall_average = sum(
        result["recall_at_4"]
        for result in results
    ) / len(results)

    hit_rate_average = sum(
        result["hit_rate_at_4"]
        for result in results
    ) / len(results)

    latency_average = sum(
        result["latency_seconds"]
        for result in results
    ) / len(results)

    budget_compliance = sum(
        result["budget_respected"]
        for result in results
    ) / len(results)

else:
    precision_average = 0
    recall_average = 0
    hit_rate_average = 0
    latency_average = 0
    budget_compliance = 0


report = {
    "status": "success" if not errors else "partial",
    "top_k": TOP_K,
    "evaluated_users": len(results),
    "precision_at_4": round(
        precision_average,
        4,
    ),
    "recall_at_4": round(
        recall_average,
        4,
    ),
    "hit_rate_at_4": round(
        hit_rate_average,
        4,
    ),
    "catalog_coverage": round(
        len(recommended_products)
        / len(all_products),
        4,
    ) if all_products else 0,
    "average_latency_seconds": round(
        latency_average,
        4,
    ),
    "budget_compliance": round(
        budget_compliance,
        4,
    ),
    "errors": errors,
    "details": results,
}

REPORT_PATH.parent.mkdir(
    parents=True,
    exist_ok=True,
)

with REPORT_PATH.open(
    "w",
    encoding="utf-8",
) as file:
    json.dump(
        report,
        file,
        ensure_ascii=False,
        indent=2,
    )
    file.write("\n")

print("✅ Évaluation terminée")
print(
    f"Utilisateurs évalués : {len(results)}"
)
print(
    "Precision@4 : "
    f"{report['precision_at_4']}"
)
print(
    "Recall@4 : "
    f"{report['recall_at_4']}"
)
print(
    "Hit Rate@4 : "
    f"{report['hit_rate_at_4']}"
)
print(
    "Couverture catalogue : "
    f"{report['catalog_coverage']}"
)
print(
    "Latence moyenne : "
    f"{report['average_latency_seconds']} s"
)
print(
    "Rapport créé : "
    f"{REPORT_PATH}"
)