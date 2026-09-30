import csv
import json
from pathlib import Path

from recommendation_engine import (
    build_recommendation,
    generate_explanation,
)


FEATURES_PATH = Path("data/processed/ai_features.csv")
REPORT_PATH = Path("reports/explainability_report.json")

errors = []
results = []


def check(condition, message):
    if not condition:
        errors.append(message)


def read_users():
    with FEATURES_PATH.open("r", encoding="utf-8", newline="") as file:
        return sorted({row["user_id"] for row in csv.DictReader(file)})


def test_user(user_id):
    result = build_recommendation(user_id)

    check(result["status"] == "success", f"{user_id} : recommandation non générée")
    routine = result["routine"]
    check(bool(routine), f"{user_id} : routine vide")

    if not routine:
        return

    ids = [product["product_id"] for product in routine]
    check(len(ids) == len(set(ids)), f"{user_id} : doublon dans la routine")
    check(len(ids) <= 4, f"{user_id} : plus de 4 produits")

    if result["budget"] is not None:
        check(result["total_price"] <= result["budget"], f"{user_id} : budget dépassé")

    check("fallbacks" in result, f"{user_id} : repli non signalé")

    for product in routine:
        pid = product["product_id"]
        text = " | ".join(product["reasons"])
        score = product.get("score")

        check(len(product["reasons"]) >= 3, f"{user_id} : explication trop courte ({pid})")
        check(score is not None and 0 <= score <= 1, f"{user_id} : score invalide ({pid})")

        # Cohérence explication <-> attributs réels
        if product["skin_match"] == 1:
            check("type de peau compatible" in text, f"{user_id} : peau non expliquée ({pid})")
        else:
            check("type de peau différent" in text, f"{user_id} : écart de peau non signalé ({pid})")

        if product["finish_match"] == 1:
            check("fini correspondant" in text, f"{user_id} : fini non expliqué ({pid})")
        else:
            check("alternative au fini" in text, f"{user_id} : écart de fini non signalé ({pid})")

        check(f"{product['price']:.2f} €" in text, f"{user_id} : prix absent ({pid})")

    # Les explications ne sont pas identiques par défaut
    all_reasons = {tuple(product["reasons"]) for product in routine}
    check(len(all_reasons) == len(routine), f"{user_id} : explications identiques")

    results.append(
        {
            "user_id": user_id,
            "products_count": len(routine),
            "total_price": result["total_price"],
            "budget": result["budget"],
            "fallbacks": result["fallbacks"],
        }
    )


def test_counterfactuals():
    """Modifier une variable doit modifier l'explication correspondante."""
    base = {
        "category": "blush",
        "price": "20",
        "max_budget": "50",
        "preferred_finish": "mat",
        "finish": "mat",
        "skin_match": "1",
        "finish_match": "1",
        "available_flag": "1",
        "interaction_signal": "",
        "compatibility_score": 0.8,
    }

    reference = generate_explanation(base)

    changed_finish = generate_explanation({**base, "finish": "glowy", "finish_match": "0"})
    check(reference != changed_finish, "contre-test : le changement de fini ne modifie pas l'explication")

    changed_budget = generate_explanation({**base, "max_budget": "25"})
    check(reference != changed_budget, "contre-test : le changement de budget ne modifie pas l'explication")

    changed_skin = generate_explanation({**base, "skin_match": "0"})
    check(reference != changed_skin, "contre-test : le changement de peau ne modifie pas l'explication")

    with_history = generate_explanation({**base, "interaction_signal": "positive"})
    check(
        "interaction positive enregistrée" in " | ".join(with_history),
        "contre-test : interaction positive non expliquée",
    )


def test_unknown_user():
    try:
        build_recommendation("user_inconnu")
        errors.append("utilisateur inconnu : aucune erreur levée")
    except ValueError:
        pass


user_ids = read_users()

for uid in user_ids:
    try:
        test_user(uid)
    except Exception as error:
        errors.append(f"{uid} : {error}")

test_counterfactuals()
test_unknown_user()

report = {
    "status": "success" if not errors else "failed",
    "users_tested": len(user_ids),
    "checks": [
        "routine non vide, sans doublon, <= 4 produits",
        "budget total respecté",
        "score compris entre 0 et 1",
        "explication cohérente avec peau, fini et prix réels",
        "explications distinctes dans une routine",
        "contre-tests : fini, budget, peau, historique",
        "utilisateur inconnu géré",
        "replis signalés",
    ],
    "fallback_users": [r["user_id"] for r in results if any(r["fallbacks"].values())],
    "results": results,
    "errors": errors,
}

REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

with REPORT_PATH.open("w", encoding="utf-8") as file:
    json.dump(report, file, ensure_ascii=False, indent=2)
    file.write("\n")

if errors:
    print("❌ Test d'explicabilité échoué")
    for error in errors:
        print(f"- {error}")
    raise SystemExit(1)

print("✅ Test d'explicabilité réussi")
print(f"Utilisateurs testés : {len(user_ids)}")
print("✅ Explications cohérentes avec les attributs réels")
print("✅ Contre-tests réussis (fini, budget, peau, historique)")
print("✅ Budgets respectés, aucun doublon")
print(f"Rapport créé : {REPORT_PATH}")