import argparse
import csv
import json
from pathlib import Path


FEATURES_PATH = Path("data/processed/ai_features.csv")
REPORT_DIR = Path("reports")


def read_features():
    with FEATURES_PATH.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as file:
        return list(csv.DictReader(file))


def to_float(value):
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def interaction_score(signal):
    if signal == "positive":
        return 1.0

    if signal in {
        "negative",
        "sampled_non_interaction",
    }:
        return 0.0

    return 0.5


def calculate_score(row, use_interactions=True):
    price = to_float(row.get("price"))
    budget = to_float(row.get("max_budget"))

    if price is not None and budget not in (None, 0):
        budget_score = max(
            0.0,
            min(1.0, 1 - (price / budget)),
        )
    else:
        budget_score = 0.0

    if "history_match" in row:
        history_score = to_int(
            row.get("history_match")
        )
    else:
        history_score = 0.5

    if use_interactions:
        interaction_component = interaction_score(
            row.get("interaction_signal", "")
        )
    else:
        interaction_component = 0.5

    score = (
        0.25 * to_int(row.get("skin_match"))
        + 0.20 * to_int(row.get("finish_match"))
        + 0.20 * budget_score
        + 0.10 * to_int(row.get("available_flag"))
        + 0.15 * interaction_component
        + 0.10 * history_score
    )

    return round(score, 4)


def filter_candidates(rows):
    available_rows = [
        row
        for row in rows
        if to_int(row.get("available_flag")) == 1
    ]

    budget_rows = []

    for row in available_rows:
        price = to_float(row.get("price"))
        budget = to_float(row.get("max_budget"))

        if (
            price is not None
            and budget is not None
            and price <= budget
        ):
            budget_rows.append(row)

    if budget_rows:
        candidates = budget_rows
        budget_fallback = False
    else:
        candidates = available_rows
        budget_fallback = True

    exact_skin_rows = [
        row
        for row in candidates
        if to_int(row.get("skin_match")) == 1
    ]

    if exact_skin_rows:
        candidates = exact_skin_rows
        skin_fallback = False
    else:
        skin_fallback = True

    return candidates, budget_fallback, skin_fallback


def generate_explanation(row):
    explanations = []

    category = row.get("category") or (
        "catégorie non précisée"
    )
    price = to_float(row.get("price"))
    budget = to_float(row.get("max_budget"))
    preferred_finish = row.get("preferred_finish")
    actual_finish = row.get("finish")

    explanations.append(
        "catégorie "
        f"{category} sélectionnée pour compléter la routine"
    )

    if to_int(row.get("skin_match")) == 1:
        explanations.append(
            "type de peau compatible"
        )
    else:
        explanations.append(
            "type de peau différent, produit conservé "
            "comme alternative"
        )

    if to_int(row.get("finish_match")) == 1:
        explanations.append(
            "fini correspondant à la préférence"
        )
    elif actual_finish:
        explanations.append(
            f"fini {actual_finish} proposé comme alternative "
            f"au fini {preferred_finish}"
        )

    if price is not None and budget not in (None, 0):
        ratio = round((price / budget) * 100)

        explanations.append(
            f"prix de {price:.2f} €, soit {ratio}% du budget"
        )

    if to_int(row.get("available_flag")) == 1:
        explanations.append(
            "produit disponible dans le catalogue"
        )

    if row.get("interaction_signal") == "positive":
        explanations.append(
            "interaction positive enregistrée"
        )

    score = row.get("compatibility_score")

    if score is not None:
        explanations.append(
            "score de compatibilité : "
            f"{float(score) * 100:.1f}/100"
        )

    return explanations


def select_routine(
    candidates,
    budget,
    max_products=4,
):
    ranked = sorted(
        candidates,
        key=lambda row: row["compatibility_score"],
        reverse=True,
    )

    selected = []
    selected_categories = set()
    selected_ids = set()
    total_price = 0.0

    for row in ranked:
        if len(selected) >= max_products:
            break

        product_id = row.get("product_id")
        category = row.get("category") or (
            "non catégorisé"
        )
        price = to_float(row.get("price"))

        if price is None or product_id in selected_ids:
            continue

        if category in selected_categories:
            continue

        if (
            budget is not None
            and total_price + price > budget
        ):
            continue

        selected.append(row)
        selected_ids.add(product_id)
        selected_categories.add(category)
        total_price += price

    if len(selected) < max_products:
        for row in ranked:
            if len(selected) >= max_products:
                break

            product_id = row.get("product_id")
            price = to_float(row.get("price"))

            if price is None or product_id in selected_ids:
                continue

            if (
                budget is not None
                and total_price + price > budget
            ):
                continue

            selected.append(row)
            selected_ids.add(product_id)
            total_price += price

    return selected, round(total_price, 2)


def build_recommendation(
    user_id,
    max_products=4,
    use_interactions=True,
    feature_rows=None,
):
    if feature_rows is None:
        rows = read_features()
    else:
        rows = feature_rows

    user_rows = [
        row
        for row in rows
        if row.get("user_id") == user_id
    ]

    if not user_rows:
        raise ValueError(
            f"Utilisateur inconnu : {user_id}"
        )

    candidates, budget_fallback, skin_fallback = (
        filter_candidates(user_rows)
    )

    for row in candidates:
        row["compatibility_score"] = (
            calculate_score(
                row,
                use_interactions,
            )
        )

    budget = to_float(
        user_rows[0].get("max_budget")
    )

    selected, total_price = select_routine(
        candidates,
        budget,
        max_products,
    )

    routine = []

    for row in selected:
        routine.append(
            {
                "product_id": row.get("product_id"),
                "brand": row.get("brand"),
                "name": row.get("name"),
                "category": row.get("category"),
                "price": to_float(row.get("price")),
                "score": row["compatibility_score"],
                "reasons": generate_explanation(row),
            }
        )

    if routine:
        status = "success"
        message = "Routine générée avec succès."
    else:
        status = "no_compatible_product"
        message = (
            "Aucun produit ne respecte les contraintes."
        )

    return {
        "status": status,
        "message": message,
        "user_id": user_id,
        "budget": budget,
        "total_price": total_price,
        "products_count": len(routine),
        "routine": routine,
        "fallbacks": {
            "budget": budget_fallback,
            "skin_type": skin_fallback,
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Générer une routine Beauty Advisor"
        )
    )

    parser.add_argument(
        "--user-id",
        required=True,
        help="Identifiant de l'utilisateur",
    )

    parser.add_argument(
        "--max-products",
        type=int,
        default=4,
        help="Nombre maximal de produits",
    )

    args = parser.parse_args()

    result = build_recommendation(
        args.user_id,
        args.max_products,
    )

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        REPORT_DIR
        / f"recommendation_{args.user_id}.json"
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2,
        )
        file.write("\n")

    print("✅ Recommandation générée")
    print(f"Utilisateur : {args.user_id}")
    print(
        "Produits sélectionnés : "
        f"{result['products_count']}"
    )
    print(
        "Budget total : "
        f"{result['total_price']:.2f} €"
    )
    print(f"Rapport créé : {output_path}")


if __name__ == "__main__":
    main()