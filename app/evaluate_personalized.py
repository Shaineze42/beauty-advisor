import csv
import json
import random
import time
from collections import defaultdict
from pathlib import Path

from recommendation_engine import (
    build_recommendation,
    filter_candidates,
    select_routine,
    to_float,
    to_int,
)


FEATURES_PATH = Path("data/processed/ai_features.csv")
TRAIN_PATH = Path("data/processed/train.csv")
TEST_PATH = Path("data/processed/test.csv")
AI_REPORT_PATH = Path("reports/ai_data_report.json")
REPORT_PATH = Path("reports/evaluation_personalized_report.json")

TOP_K = 4
BASELINE_SEED = 42


def read_csv(path):
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def mean(values):
    values = list(values)
    return round(sum(values) / len(values), 4) if values else 0.0


def build_train_context(features, train_rows):
    """
    Reconstruit le signal d'interaction et l'historique UNIQUEMENT à partir
    du train : le test n'influence jamais les recommandations.
    """
    profiles = defaultdict(
        lambda: {"products": set(), "categories": set(), "finishes": set()}
    )
    signals = {}

    for row in train_rows:
        key = (row["user_id"], row["product_id"])

        if row.get("label") == "1":
            profile = profiles[row["user_id"]]
            profile["products"].add(row["product_id"])
            profile["categories"].add(row.get("category", ""))
            profile["finishes"].add(row.get("finish", ""))
            signals[key] = "positive"
        elif row.get("label") == "0":
            signals[key] = "sampled_non_interaction"

    for row in features:
        profile = profiles[row["user_id"]]
        row["interaction_signal"] = signals.get(
            (row["user_id"], row["product_id"]), ""
        )
        row["history_match"] = int(
            row["product_id"] in profile["products"]
            or (
                row.get("category", "") in profile["categories"]
                and row.get("finish", "") in profile["finishes"]
            )
        )


def relevance_flags(recommended, relevant_rows):
    """
    Niveaux de pertinence d'un produit recommandé face aux positifs du test :
      exact    : même product_id ;
      category : même catégorie ;
      finish   : même catégorie ET même fini ;
      skin     : même catégorie ET même type de peau cible ;
      strict   : même catégorie ET (même fini OU même type de peau).
    La catégorie est TOUJOURS exigée pour les niveaux fonctionnels.
    """
    flags = {"exact": False, "category": False, "finish": False, "skin": False}

    for relevant in relevant_rows:
        same_category = recommended.get("category") == relevant.get("category")

        if recommended.get("product_id") == relevant.get("product_id"):
            flags["exact"] = True
        if same_category:
            flags["category"] = True
            if recommended.get("finish") == relevant.get("finish"):
                flags["finish"] = True
            if recommended.get("suitable_skin_type") == relevant.get(
                "suitable_skin_type"
            ):
                flags["skin"] = True

    flags["strict"] = flags["finish"] or flags["skin"]
    return flags


def routine_relevance(recommended_rows, relevant_rows):
    counts = {"exact": 0, "category": 0, "finish": 0, "skin": 0, "strict": 0}

    for recommended in recommended_rows:
        flags = relevance_flags(recommended, relevant_rows)
        for name in counts:
            counts[name] += int(flags[name])

    return counts


def score_row_metrics(counts, relevant_count):
    return {
        "precision_exact": round(counts["exact"] / TOP_K, 4),
        "recall_exact": round(counts["exact"] / relevant_count, 4),
        "precision_category": round(counts["category"] / TOP_K, 4),
        "precision_functional": round(counts["strict"] / TOP_K, 4),
        "hit_category": int(counts["category"] > 0),
        "hit_functional": int(counts["strict"] > 0),
    }


def business_metrics(routine, budget, latency):
    """Indicateurs métier, indépendants des labels du test."""
    n = len(routine)
    ids = [product["product_id"] for product in routine]
    categories = {product["category"] for product in routine}
    total_price = round(sum(product["price"] or 0 for product in routine), 2)

    return {
        "products_count": n,
        "fill_rate": round(n / TOP_K, 4),
        "compatibility_rate": mean(
            int(product["skin_match"] == 1 or product["finish_match"] == 1)
            for product in routine
        ),
        "availability_rate": mean(product["available"] for product in routine),
        "budget_respected": budget is None or total_price <= budget,
        "no_duplicates": len(ids) == len(set(ids)),
        "max_products_respected": n <= TOP_K,
        "distinct_categories": len(categories),
        "explanation_coverage": mean(
            int(len(product.get("reasons", [])) >= 3) for product in routine
        ),
        "latency_seconds": round(latency, 4),
    }


def baseline_routine(strategy, user_rows, user_id, seen_ids):
    """
    Baselines évaluées sur les MÊMES candidats (mêmes filtres), le même K
    et le même budget que le moteur complet ; seul le classement change.
    """
    eligible = [r for r in user_rows if r["product_id"] not in seen_ids]
    candidates, _, _ = filter_candidates(eligible)
    copies = [row.copy() for row in candidates]

    if strategy == "random":
        rng = random.Random(f"{BASELINE_SEED}-{user_id}")
        for row in copies:
            row["compatibility_score"] = rng.random()
    elif strategy == "skin_finish_only":
        for row in copies:
            row["compatibility_score"] = (
                0.5 * to_int(row.get("skin_match"))
                + 0.5 * to_int(row.get("finish_match"))
            )
    else:
        raise ValueError(strategy)

    budget = to_float(user_rows[0].get("max_budget"))
    selected, _ = select_routine(copies, budget, TOP_K)
    return selected


def main():
    features = read_csv(FEATURES_PATH)
    train_rows = read_csv(TRAIN_PATH)
    test_rows = read_csv(TEST_PATH)

    build_train_context(features, train_rows)

    feature_by_product = {}
    for row in features:
        feature_by_product.setdefault(row["product_id"], row)

    rows_by_user = defaultdict(list)
    for row in features:
        rows_by_user[row["user_id"]].append(row)

    seen_by_user = defaultdict(set)
    for row in train_rows:
        if row.get("label") == "1":
            seen_by_user[row["user_id"]].add(row["product_id"])

    relevant_rows_by_user = defaultdict(list)
    for row in test_rows:
        if row.get("label") == "1":
            relevant_rows_by_user[row["user_id"]].append(row)

    results = []
    errors = []
    recommended_catalog = set()
    baseline_scores = {"random": [], "skin_finish_only": []}
    business_results = []

    for user_id in sorted(relevant_rows_by_user):
        relevant_rows = relevant_rows_by_user[user_id]
        relevant_ids = {row["product_id"] for row in relevant_rows}

        try:
            start = time.perf_counter()
            recommendation = build_recommendation(
                user_id,
                max_products=TOP_K,
                use_interactions=True,
                feature_rows=features,
                exclude_product_ids=seen_by_user[user_id],
            )
            latency = time.perf_counter() - start

            routine = recommendation["routine"]
            recommended_rows = [
                feature_by_product[product["product_id"]] for product in routine
            ]
            counts = routine_relevance(recommended_rows, relevant_rows)
            metrics = score_row_metrics(counts, len(relevant_ids))
            business = business_metrics(
                routine, recommendation["budget"], latency
            )
            recommended_catalog.update(product["product_id"] for product in routine)

            results.append(
                {
                    "user_id": user_id,
                    "relevant_products": len(relevant_ids),
                    "exact_hits": counts["exact"],
                    "category_hits": counts["category"],
                    "functional_hits": counts["strict"],
                    "fallbacks": recommendation["fallbacks"],
                    **metrics,
                }
            )
            business_results.append({"user_id": user_id, **business})

            for strategy in baseline_scores:
                selected = baseline_routine(
                    strategy, rows_by_user[user_id], user_id, seen_by_user[user_id]
                )
                base_counts = routine_relevance(selected, relevant_rows)
                baseline_scores[strategy].append(
                    score_row_metrics(base_counts, len(relevant_ids))
                )

        except Exception as error:
            errors.append({"user_id": user_id, "error": str(error)})

    def aggregate(rows, keys):
        return {key: mean(row[key] for row in rows) for key in keys}

    relevance_keys = [
        "precision_exact",
        "recall_exact",
        "precision_category",
        "precision_functional",
        "hit_category",
        "hit_functional",
    ]
    business_keys = [
        "fill_rate",
        "compatibility_rate",
        "availability_rate",
        "explanation_coverage",
        "latency_seconds",
    ]

    all_products = {row["product_id"] for row in features}
    ai_meta = {}
    if AI_REPORT_PATH.exists():
        with AI_REPORT_PATH.open("r", encoding="utf-8") as file:
            ai_meta = json.load(file)

    n = len(results)

    report = {
        "status": "success" if not errors else "partial",
        "evaluation_mode": "train_history_only_seen_products_excluded",
        "top_k": TOP_K,
        "dataset_version": ai_meta.get("dataset_version"),
        "source_hash": ai_meta.get("source_hash"),
        "split": ai_meta.get("split"),
        "evaluated_users": n,
        "business_metrics": {
            **aggregate(business_results, business_keys),
            "budget_compliance": mean(r["budget_respected"] for r in business_results),
            "no_duplicates_rate": mean(r["no_duplicates"] for r in business_results),
            "max_products_respected_rate": mean(
                r["max_products_respected"] for r in business_results
            ),
            "average_distinct_categories": mean(
                r["distinct_categories"] for r in business_results
            ),
            "catalog_coverage": round(
                len(recommended_catalog) / len(all_products), 4
            ) if all_products else 0,
        },
        "diagnostic_metrics": aggregate(results, relevance_keys),
        "baselines": {
            "random_eligible": aggregate(baseline_scores["random"], relevance_keys),
            "skin_finish_only": aggregate(
                baseline_scores["skin_finish_only"], relevance_keys
            ),
            "beauty_advisor": aggregate(results, relevance_keys),
        },
        "metric_definitions": {
            "precision_exact": "produits recommandés identiques à un positif du test / K",
            "precision_functional": (
                "même catégorie ET (même fini OU même type de peau) "
                "qu'un positif du test / K"
            ),
            "hit_category": "au moins un produit de même catégorie qu'un positif du test",
            "hit_functional": "au moins un produit fonctionnellement équivalent",
            "compatibility_rate": "part des produits compatibles peau OU fini",
            "fill_rate": "produits recommandés / K",
        },
        "limits": [
            "données synthétiques : 20 utilisateurs, 50 produits, 100 interactions",
            "la pertinence fonctionnelle reprend la règle peau OU fini utilisée "
            "pour générer les interactions (évaluation en partie circulaire)",
            "les négatifs échantillonnés ne sont pas de vrais rejets utilisateurs",
            "la précision exacte reste un indicateur de diagnostic : plusieurs "
            "produits différents peuvent convenir à la même utilisatrice",
            "le fill rate est limité par le budget total de la routine",
        ],
        "errors": errors,
        "details": results,
        "business_details": business_results,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with REPORT_PATH.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")

    bm = report["business_metrics"]
    dm = report["diagnostic_metrics"]

    print("✅ Évaluation terminée")
    print(f"Utilisateurs évalués : {n}")
    print("--- Métriques métier ---")
    print(f"Compatibilité : {bm['compatibility_rate']} | Budget : {bm['budget_compliance']}")
    print(f"Disponibilité : {bm['availability_rate']} | Fill rate : {bm['fill_rate']}")
    print(f"Explications : {bm['explanation_coverage']} | Latence moyenne : {bm['latency_seconds']} s")
    print("--- Diagnostic (vs test) ---")
    print(f"Precision exacte : {dm['precision_exact']} | Precision fonctionnelle : {dm['precision_functional']}")
    print(f"Hit rate catégorie : {dm['hit_category']} | Hit rate fonctionnel : {dm['hit_functional']}")
    print("--- Baselines (precision fonctionnelle) ---")
    for name, values in report["baselines"].items():
        print(f"{name} : {values['precision_functional']}")
    print(f"Rapport créé : {REPORT_PATH}")


if __name__ == "__main__":
    main()