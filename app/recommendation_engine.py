import argparse
import csv
import json
from pathlib import Path


FEATURES_PATH = Path("data/processed/ai_features.csv")
REPORT_DIR = Path("reports")

# Poids du score de compatibilité (testés : une version donnant plus de
# poids à la peau et au fini a donné de moins bons résultats).
SCORE_WEIGHTS = {
    "skin_match": 0.25,
    "finish_match": 0.20,
    "budget_score": 0.20,
    "availability": 0.10,
    "interaction": 0.15,
    "history_match": 0.10,
}

assert abs(sum(SCORE_WEIGHTS.values()) - 1.0) < 1e-9, (
    "La somme des poids doit valoir 1."
)


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

    if signal in {"negative", "sampled_non_interaction"}:
        return 0.0

    return 0.5


def budget_score_of(row):
    price = to_float(row.get("price"))
    budget = to_float(row.get("max_budget"))

    if price is None or budget in (None, 0):
        return 0.0

    return max(0.0, min(1.0, 1 - (price / budget)))


def calculate_score(row, use_interactions=True):
    if "history_match" in row:
        history_score = to_int(row.get("history_match"))
    else:
        history_score = 0.5

    if use_interactions:
        interaction_component = interaction_score(
            row.get("interaction_signal", "")
        )
    else:
        interaction_component = 0.5

    score = (
        SCORE_WEIGHTS["skin_match"] * to_int(row.get("skin_match"))
        + SCORE_WEIGHTS["finish_match"] * to_int(row.get("finish_match"))
        + SCORE_WEIGHTS["budget_score"] * budget_score_of(row)
        + SCORE_WEIGHTS["availability"] * to_int(row.get("available_flag"))
        + SCORE_WEIGHTS["interaction"] * interaction_component
        + SCORE_WEIGHTS["history_match"] * history_score
    )

    return round(score, 4)


def is_compatible(row):
    """
    Règle métier unique de compatibilité : le produit convient au type
    de peau déclaré OU au fini préféré. Cette règle est partagée par le
    moteur, l'évaluation et la génération des données.
    """
    return (
        to_int(row.get("skin_match")) == 1
        or to_int(row.get("finish_match")) == 1
    )


def filter_candidates(rows):
    """
    Filtres successifs : disponibilité, budget strict (price <= budget),
    compatibilité. Si un filtre vide la liste, un repli est appliqué et
    signalé dans `fallbacks`.
    """
    available_rows = [
        row for row in rows if to_int(row.get("available_flag")) == 1
    ]

    budget_rows = []

    for row in available_rows:
        price = to_float(row.get("price"))
        budget = to_float(row.get("max_budget"))

        if price is not None and budget is not None and price <= budget:
            budget_rows.append(row)

    if budget_rows:
        candidates = budget_rows
        budget_fallback = False
    else:
        candidates = available_rows
        budget_fallback = True

    compatible_rows = [row for row in candidates if is_compatible(row)]

    if compatible_rows:
        candidates = compatible_rows
        skin_fallback = False
    else:
        skin_fallback = True

    return candidates, budget_fallback, skin_fallback


def generate_explanation(row):
    explanations = []

    category = row.get("category") or "catégorie non précisée"
    price = to_float(row.get("price"))
    budget = to_float(row.get("max_budget"))
    preferred_finish = row.get("preferred_finish")
    actual_finish = row.get("finish")

    explanations.append(
        f"catégorie {category} sélectionnée pour compléter la routine"
    )

    if to_int(row.get("skin_match")) == 1:
        explanations.append("type de peau compatible")
    else:
        explanations.append(
            "type de peau différent, produit conservé comme alternative"
        )

    if to_int(row.get("finish_match")) == 1:
        explanations.append("fini correspondant à la préférence")
    elif actual_finish:
        explanations.append(
            f"fini {actual_finish} proposé comme alternative "
            f"au fini {preferred_finish}"
        )

    if price is not None and budget not in (None, 0):
        ratio = round((price / budget) * 100)
        explanations.append(f"prix de {price:.2f} €, soit {ratio}% du budget")

    if to_int(row.get("available_flag")) == 1:
        explanations.append("produit disponible dans le catalogue")

    if row.get("interaction_signal") == "positive":
        explanations.append("interaction positive enregistrée")

    score = row.get("compatibility_score")

    if score is not None:
        explanations.append(
            f"score de compatibilité : {float(score) * 100:.1f}/100"
        )

    return explanations


def select_routine(candidates, budget, max_products=4):
    """
    Passe 1 : meilleur produit par catégorie (diversité de la routine).
    Passe 2 : complète avec les meilleurs restants si la routine n'est
    pas pleine. Le budget total n'est jamais dépassé.
    """
    ranked = sorted(
        candidates,
        key=lambda row: (-row["compatibility_score"], row.get("product_id", "")),
    )

    selected = []
    selected_categories = set()
    selected_ids = set()
    total_price = 0.0

    for row in ranked:
        if len(selected) >= max_products:
            break

        product_id = row.get("product_id")
        category = row.get("category") or "non catégorisé"
        price = to_float(row.get("price"))

        if price is None or product_id in selected_ids:
            continue

        if category in selected_categories:
            continue

        if budget is not None and total_price + price > budget:
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

            if budget is not None and total_price + price > budget:
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
    exclude_product_ids=None,
):
    rows = read_features() if feature_rows is None else feature_rows

    user_rows = [row for row in rows if row.get("user_id") == user_id]

    if not user_rows:
        raise ValueError(f"Utilisateur inconnu : {user_id}")

    # Produits déjà connus de l'utilisatrice, à ne pas re-proposer
    # (utilisé par l'évaluation : on ne recommande pas ce qui est déjà vu).
    excluded = set(exclude_product_ids or [])
    eligible_rows = [
        row for row in user_rows if row.get("product_id") not in excluded
    ]

    candidates, budget_fallback, skin_fallback = filter_candidates(
        eligible_rows
    )

    for row in candidates:
        row["compatibility_score"] = calculate_score(row, use_interactions)

    budget = to_float(user_rows[0].get("max_budget"))

    selected, total_price = select_routine(candidates, budget, max_products)

    routine = []

    for row in selected:
        routine.append(
            {
                "product_id": row.get("product_id"),
                "brand": row.get("brand"),
                "name": row.get("name"),
                "category": row.get("category"),
                "finish": row.get("finish"),
                "suitable_skin_type": row.get("suitable_skin_type"),
                "price": to_float(row.get("price")),
                "skin_match": to_int(row.get("skin_match")),
                "finish_match": to_int(row.get("finish_match")),
                "available": to_int(row.get("available_flag")),
                "score": row["compatibility_score"],
                "reasons": generate_explanation(row),
            }
        )

    if routine:
        status = "success"
        message = "Routine générée avec succès."
    else:
        status = "no_compatible_product"
        message = "Aucun produit ne respecte les contraintes."

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
        description="Générer une routine Beauty Advisor"
    )
    parser.add_argument(
        "--user-id", required=True, help="Identifiant de l'utilisateur"
    )
    parser.add_argument(
        "--max-products", type=int, default=4, help="Nombre maximal de produits"
    )

    args = parser.parse_args()

    result = build_recommendation(args.user_id, args.max_products)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORT_DIR / f"recommendation_{args.user_id}.json"

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
        file.write("\n")

    print("✅ Recommandation générée")
    print(f"Utilisateur : {args.user_id}")
    print(f"Produits sélectionnés : {result['products_count']}")
    print(f"Budget total : {result['total_price']:.2f} €")
    print(f"Rapport créé : {output_path}")


if __name__ == "__main__":
    main()