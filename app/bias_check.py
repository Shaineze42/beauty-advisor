"""
Tests de biais et d'équité de Beauty Advisor.

Deux questions :
  1. La qualité des routines est-elle comparable entre groupes d'utilisatrices
     (type de peau, carnation, sous-ton, fini préféré, niveau de budget) ?
  2. L'exposition du catalogue est-elle équilibrée (marques, catégories) ?

Un écart n'est qualifié d'AVERTISSEMENT que si tous les groupes comparés ont au
moins 10 personnes. En dessous, l'écart est INDICATIF : avec 20 utilisatrices
synthétiques, un groupe de 3 à 8 personnes suffit à créer un écart sans
signification statistique. Les écarts attendus par construction (le nombre de
produits d'une routine dépend du budget) sont signalés comme tels.
Écrit reports/bias_report.json.
"""
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from recommendation_engine import build_recommendation, read_features


USERS_PATH = Path("data/processed/users_raw.csv")
EVAL_REPORT_PATH = Path("reports/evaluation_personalized_report.json")
REPORT_PATH = Path("reports/bias_report.json")

MIN_GROUP_SIZE = 3
SIGNIFICANT_GROUP_SIZE = 10
MAX_GAP = 0.30
MAX_BRAND_SHARE = 0.40
GROUP_ATTRIBUTES = ["skin_type", "complexion", "undertone", "preferred_finish", "budget_tier"]


def budget_tier(budget):
    if budget <= 30:
        return "budget <= 30 EUR"
    if budget <= 60:
        return "budget 31-60 EUR"
    return "budget > 60 EUR"


def read_users():
    with USERS_PATH.open("r", encoding="utf-8", newline="") as file:
        users = {row["user_id"]: row for row in csv.DictReader(file)}

    for user in users.values():
        user["budget_tier"] = budget_tier(float(user["max_budget"]))

    return users


def mean(values):
    values = list(values)
    return round(sum(values) / len(values), 4) if values else None


def group_quality(users, evaluation):
    """Qualité moyenne par groupe, à partir de l'évaluation déjà calculée."""
    diagnostic = {row["user_id"]: row for row in evaluation["details"]}
    business = {row["user_id"]: row for row in evaluation["business_details"]}
    results = {}
    warnings = []
    indicative = []

    for attribute in GROUP_ATTRIBUTES:
        groups = defaultdict(list)

        for user_id in diagnostic:
            groups[users[user_id][attribute]].append(user_id)

        stats = {}

        for value, ids in sorted(groups.items()):
            stats[value] = {
                "users": len(ids),
                "compatibility_rate": mean(business[i]["compatibility_rate"] for i in ids),
                "fill_rate": mean(business[i]["fill_rate"] for i in ids),
                "hit_functional": mean(diagnostic[i]["hit_functional"] for i in ids),
            }

        comparable = {k: v for k, v in stats.items() if v["users"] >= MIN_GROUP_SIZE}
        smallest = min((v["users"] for v in comparable.values()), default=0)
        gaps = {}

        for metric in ("compatibility_rate", "fill_rate", "hit_functional"):
            values = [v[metric] for v in comparable.values()]
            gaps[metric] = round(max(values) - min(values), 4) if len(values) >= 2 else None

            if gaps[metric] is None or gaps[metric] <= MAX_GAP:
                continue

            message = f"{attribute} : écart de {gaps[metric]} sur {metric}"

            if attribute == "budget_tier" and metric == "fill_rate":
                indicative.append(message + " (attendu : le budget total limite le nombre de produits)")
            elif smallest < SIGNIFICANT_GROUP_SIZE:
                indicative.append(message + f" (indicatif : plus petit groupe = {smallest} personnes)")
            else:
                warnings.append(message)

        results[attribute] = {"groups": stats, "max_gap": gaps}

    return results, warnings, indicative


def exposure(users):
    """Répartition des produits réellement recommandés à tous les profils."""
    rows = read_features()
    brands = Counter()
    categories = Counter()
    products = set()
    total = 0

    for user_id in users:
        result = build_recommendation(user_id, feature_rows=rows)

        for product in result["routine"]:
            brands[product["brand"]] += 1
            categories[product["category"]] += 1
            products.add(product["product_id"])
            total += 1

    top_brand, top_count = brands.most_common(1)[0] if brands else (None, 0)
    share = round(top_count / total, 4) if total else 0
    warnings = []

    if share > MAX_BRAND_SHARE:
        warnings.append(
            f"marque dominante : {top_brand} représente {share:.0%} des recommandations"
        )

    return {
        "recommendations_total": total,
        "distinct_products_recommended": len(products),
        "brand_share": {b: round(c / total, 4) for b, c in brands.most_common()},
        "category_share": {c: round(n / total, 4) for c, n in categories.most_common()},
        "top_brand": top_brand,
        "top_brand_share": share,
        "max_brand_share_threshold": MAX_BRAND_SHARE,
    }, warnings


def main():
    with EVAL_REPORT_PATH.open("r", encoding="utf-8") as file:
        evaluation = json.load(file)

    users = read_users()
    quality, quality_warnings, indicative_gaps = group_quality(users, evaluation)
    exposure_result, exposure_warnings = exposure(users)
    warnings = quality_warnings + exposure_warnings

    report = {
        "status": (
            "warning" if warnings else "indicative_gaps" if indicative_gaps else "success"
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset_version": evaluation.get("dataset_version"),
        "method": (
            "comparaison des métriques par groupe (écart max - min, groupes >= "
            f"{MIN_GROUP_SIZE} personnes) et mesure de la concentration par marque"
        ),
        "protected_data_note": (
            "Aucune donnée sensible (origine, santé, biométrie) n'est collectée ; "
            "carnation et sous-ton sont des attributs cosmétiques déclarés."
        ),
        "quality_by_group": quality,
        "catalog_exposure": exposure_result,
        "warnings": warnings,
        "indicative_gaps": indicative_gaps,
        "limits": [
            "20 utilisatrices synthétiques : aucun groupe n'atteint 10 personnes, les écarts sont indicatifs",
            "les écarts de fill rate entre niveaux de budget sont attendus (budget total strict)",
        ],
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Biais : {len(warnings)} avertissement(s) | {len(indicative_gaps)} écart(s) indicatif(s)")
    print(f"Marque dominante : {exposure_result['top_brand']} ({exposure_result['top_brand_share']:.0%})")
    print(f"Produits distincts recommandés : {exposure_result['distinct_products_recommended']}")

    for attribute, data in quality.items():
        print(f"  {attribute} : écarts {data['max_gap']}")

    for warning in warnings:
        print(f"⚠️  {warning}")

    for gap in indicative_gaps:
        print(f"ℹ️  {gap}")

    print(f"Rapport créé : {REPORT_PATH}")


if __name__ == "__main__":
    main()