"""Évaluation d'un jeu de poids et règle de promotion."""
import tempfile
from pathlib import Path

from beauty_ml.bridge import run_offline_evaluation
from beauty_ml.training import content_auc

# Règles métier : le produit doit TOUJOURS les respecter (même liste que le
# monitoring du modèle).
CRITICAL_RULES = [
    "budget_compliance",
    "compatibility_rate",
    "availability_rate",
    "explanation_coverage",
    "no_duplicates_rate",
    "max_products_respected_rate",
]


def evaluate(weights, X_test, y_test):
    """AUC de contenu sur le test + métriques de l'évaluation personnalisée."""
    with tempfile.TemporaryDirectory() as folder:
        report = run_offline_evaluation(weights, Path(folder) / "evaluation.json")
    business = report["business_metrics"]
    diagnostic = report["diagnostic_metrics"]
    return {
        "content_auc_test": round(content_auc(weights, X_test, y_test), 4),
        "precision_functional": diagnostic["precision_functional"],
        "hit_functional": diagnostic["hit_functional"],
        "evaluated_users": report["evaluated_users"],
        "critical": {name: business[name] for name in CRITICAL_RULES},
    }


def decide(candidate, current, min_auc_gain=0.01, max_precision_drop=0.02):
    """Faut-il promouvoir le candidat ? Trois garde-fous, dans cet ordre."""
    broken = [name for name, value in candidate["critical"].items() if value < 1.0]
    gain = round(candidate["content_auc_test"] - current["content_auc_test"], 4)
    drop = round(current["precision_functional"] - candidate["precision_functional"], 4)
    base = {"auc_gain": gain, "precision_drop": drop}
    if broken:
        return {**base, "promote": False, "reason": f"règle métier violée : {', '.join(broken)}"}
    if drop > max_precision_drop:
        return {
            **base,
            "promote": False,
            "reason": f"précision fonctionnelle en baisse de {drop} (maximum toléré {max_precision_drop})",
        }
    if gain < min_auc_gain:
        return {
            **base,
            "promote": False,
            "reason": f"gain d'AUC insuffisant ({gain:+} pour un minimum de {min_auc_gain:+})",
        }
    return {**base, "promote": True, "reason": f"AUC de contenu {gain:+}, aucune régression métier"}
