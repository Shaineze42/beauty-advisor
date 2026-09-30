import csv
import json
import time
from collections import defaultdict
from pathlib import Path

from recommendation_engine import build_recommendation


FEATURES_PATH = Path("data/processed/ai_features.csv")
TRAIN_PATH = Path("data/processed/train.csv")
TEST_PATH = Path("data/processed/test.csv")
REPORT_PATH = Path("reports/evaluation_personalized_report.json")

TOP_K = 4


def read_csv(path):
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


features = read_csv(FEATURES_PATH)
train_rows = read_csv(TRAIN_PATH)
test_rows = read_csv(TEST_PATH)

feature_by_product_id = {row["product_id"]: row for row in features}

user_profiles = defaultdict(
    lambda: {"products": set(), "categories": set(), "finishes": set()}
)

train_signals = {}

for row in train_rows:
    user_id = row["user_id"]
    product_id = row["product_id"]
    key = (user_id, product_id)

    if row.get("label") == "1":
        profile = user_profiles[user_id]
        profile["products"].add(product_id)
        profile["categories"].add(row.get("category", ""))
        profile["finishes"].add(row.get("finish", ""))
        train_signals[key] = "positive"

    elif row.get("label") == "0":
        train_signals[key] = "sampled_non_interaction"


for row in features:
    user_id = row["user_id"]
    product_id = row["product_id"]
    key = (user_id, product_id)

    row["interaction_signal"] = train_signals.get(key, "")

    profile = user_profiles[user_id]

    # CORRECTION : on exige catégorie ET fini ensemble (ou le produit
    # exact déjà vu), plutôt qu'un simple OR trop permissif qui faisait
    # "matcher" tout un rayon dès qu'un seul favori existait dedans.
    row["history_match"] = int(
        product_id in profile["products"]
        or (
            row.get("category", "") in profile["categories"]
            and row.get("finish", "") in profile["finishes"]
        )
    )


relevant_by_user = defaultdict(set)

for row in test_rows:
    if row.get("label") == "1":
        relevant_by_user[row["user_id"]].add(row["product_id"])


all_products = {row["product_id"] for row in features}

recommended_products = set()
results = []
errors = []

for user_id, relevant_products in sorted(relevant_by_user.items()):
    start_time = time.perf_counter()

    try:
        recommendation = build_recommendation(
            user_id, max_products=TOP_K, use_interactions=True, feature_rows=features
        )

        latency = time.perf_counter() - start_time

        recommended_ids = {p["product_id"] for p in recommendation["routine"]}
        hits = recommended_ids.intersection(relevant_products)

        relevant_rows = [
            row for row in test_rows
            if row["user_id"] == user_id and row.get("label") == "1"
        ]

        recommended_rows = [
            feature_by_product_id[product_id]
            for product_id in recommended_ids
            if product_id in feature_by_product_id
        ]

        category_hits = 0
        feature_hits = 0

        for recommended_row in recommended_rows:
            same_category = any(
                recommended_row.get("category") == relevant_row.get("category")
                for relevant_row in relevant_rows
            )

            same_features = any(
                recommended_row.get("category") == relevant_row.get("category")
                and recommended_row.get("finish") == relevant_row.get("finish")
                or recommended_row.get("suitable_skin_type") == relevant_row.get("suitable_skin_type")
                for relevant_row in relevant_rows
            )

            if same_category:
                category_hits += 1
            if same_features:
                feature_hits += 1

        budget = recommendation["budget"]
        total_price = recommendation["total_price"]
        budget_respected = budget is None or total_price <= budget

        recommended_products.update(recommended_ids)

        results.append(
            {
                "user_id": user_id,
                "recommended_products": len(recommended_ids),
                "relevant_products": len(relevant_products),
                "exact_hits": len(hits),
                "category_hits": category_hits,
                "feature_hits": feature_hits,
                "precision_at_4": round(len(hits) / TOP_K, 4),
                "recall_at_4": round(len(hits) / len(relevant_products), 4),
                "category_precision_at_4": round(category_hits / TOP_K, 4),
                "feature_precision_at_4": round(feature_hits / TOP_K, 4),
                "category_hit_rate_at_4": int(category_hits > 0),
                "feature_hit_rate_at_4": int(feature_hits > 0),
                "latency_seconds": round(latency, 4),
                "budget_respected": budget_respected,
            }
        )

    except Exception as error:
        errors.append({"user_id": user_id, "error": str(error)})


evaluated_users = len(results)

if evaluated_users:
    precision = sum(r["precision_at_4"] for r in results) / evaluated_users
    recall = sum(r["recall_at_4"] for r in results) / evaluated_users
    category_precision = sum(r["category_precision_at_4"] for r in results) / evaluated_users
    feature_precision = sum(r["feature_precision_at_4"] for r in results) / evaluated_users
    category_hit_rate = sum(r["category_hit_rate_at_4"] for r in results) / evaluated_users
    feature_hit_rate = sum(r["feature_hit_rate_at_4"] for r in results) / evaluated_users
    latency = sum(r["latency_seconds"] for r in results) / evaluated_users
    budget_compliance = sum(r["budget_respected"] for r in results) / evaluated_users
else:
    precision = recall = category_precision = feature_precision = 0
    category_hit_rate = feature_hit_rate = latency = budget_compliance = 0


report = {
    "status": "success" if not errors else "partial",
    "evaluation_mode": "training_interactions_only",
    "top_k": TOP_K,
    "evaluated_users": evaluated_users,
    "precision_at_4": round(precision, 4),
    "recall_at_4": round(recall, 4),
    "category_precision_at_4": round(category_precision, 4),
    "feature_precision_at_4": round(feature_precision, 4),
    "category_hit_rate_at_4": round(category_hit_rate, 4),
    "feature_hit_rate_at_4": round(feature_hit_rate, 4),
    "catalog_coverage": round(len(recommended_products) / len(all_products), 4) if all_products else 0,
    "average_latency_seconds": round(latency, 4),
    "budget_compliance": round(budget_compliance, 4),
    "errors": errors,
    "details": results,
}


REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

with REPORT_PATH.open("w", encoding="utf-8") as file:
    json.dump(report, file, ensure_ascii=False, indent=2)
    file.write("\n")


print("✅ Évaluation personnalisée terminée")
print(f"Utilisateurs évalués : {evaluated_users}")
print(f"Precision@4 exacte : {report['precision_at_4']}")
print(f"Precision fonctionnelle : {report['feature_precision_at_4']}")
print(f"Hit Rate par catégorie : {report['category_hit_rate_at_4']}")
print(f"Hit Rate fonctionnel : {report['feature_hit_rate_at_4']}")
print(f"Rapport créé : {REPORT_PATH}")