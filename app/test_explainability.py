import json
from pathlib import Path

from recommendation_engine import build_recommendation


USER_IDS = [
    "user_001",
    "user_002",
    "user_003",
]

results = []
errors = []

for user_id in USER_IDS:
    try:
        result = build_recommendation(user_id)

        if result["status"] != "success":
            errors.append(
                f"{user_id} : recommandation non générée"
            )
            continue

        routine = result["routine"]

        if not routine:
            errors.append(
                f"{user_id} : routine vide"
            )
            continue

        product_ids = [
            product["product_id"]
            for product in routine
        ]

        if len(product_ids) != len(set(product_ids)):
            errors.append(
                f"{user_id} : doublon dans la routine"
            )

        if result["budget"] is not None:
            if result["total_price"] > result["budget"]:
                errors.append(
                    f"{user_id} : budget dépassé"
                )

        for product in routine:
            reasons = product.get("reasons", [])
            score = product.get("score")

            if len(reasons) < 3:
                errors.append(
                    f"{user_id} : explication trop courte "
                    f"pour {product['product_id']}"
                )

            if score is None or not 0 <= score <= 1:
                errors.append(
                    f"{user_id} : score invalide "
                    f"pour {product['product_id']}"
                )

        results.append(
            {
                "user_id": user_id,
                "products_count": len(routine),
                "total_price": result["total_price"],
                "budget": result["budget"],
                "explanations_validated": True,
            }
        )

    except Exception as error:
        errors.append(f"{user_id} : {error}")


report = {
    "status": "success" if not errors else "failed",
    "users_tested": len(USER_IDS),
    "results": results,
    "errors": errors,
}

Path("reports").mkdir(
    parents=True,
    exist_ok=True,
)

with open(
    "reports/explainability_report.json",
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

if errors:
    print("❌ Test d'explicabilité échoué")
    for error in errors:
        print(f"- {error}")
    raise SystemExit(1)

print("✅ Test d'explicabilité réussi")
print(f"Utilisateurs testés : {len(USER_IDS)}")
print("✅ Chaque produit possède une explication")
print("✅ Les scores sont valides")
print("✅ Les budgets sont respectés")
print("✅ Aucun doublon détecté")
print(
    "Rapport créé : "
    "reports/explainability_report.json"
)