"""Détection de dérive (drift) des données d'entrée du modèle.

Mesure l'indice PSI (Population Stability Index) de chaque caractéristique
entre la référence figée dans le modèle actif et les données courantes :
  PSI < 0,10        stable
  0,10 <= PSI < 0,25  à surveiller (warning)
  PSI >= 0,25       dérive (drift)

Usage (depuis la racine du dépôt) :
  python monitoring/drift.py                # modèle actif vs données courantes
  python monitoring/drift.py --simulate     # même contrôle sur des données décalées
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

PSI_WARNING = 0.10
PSI_DRIFT = 0.25
EPSILON = 1e-4
REPORT_PATH = Path("reports/drift_report.json")
RANK = {"stable": 0, "warning": 1, "drift": 2}


def _is_binary(values):
    return set(np.unique(values)).issubset({0.0, 1.0})


def build_reference(X, feature_names):
    """Photographie de la distribution d'apprentissage (stockée dans le modèle)."""
    reference = {}
    for j, name in enumerate(feature_names):
        column = X[:, j]
        if _is_binary(column):
            reference[name] = {"type": "binaire", "p1": round(float(column.mean()), 4)}
        else:
            edges = np.unique(np.quantile(column, [0.2, 0.4, 0.6, 0.8]))
            counts = np.bincount(np.digitize(column, edges), minlength=len(edges) + 1)
            reference[name] = {
                "type": "continue",
                "edges": [round(float(e), 4) for e in edges],
                "proportions": [round(float(c) / len(column), 4) for c in counts],
            }
    return reference


def psi(expected, actual):
    expected = np.clip(np.asarray(expected, dtype=float), EPSILON, None)
    actual = np.clip(np.asarray(actual, dtype=float), EPSILON, None)
    return float(np.sum((actual - expected) * np.log(actual / expected)))


def status_of(value):
    if value >= PSI_DRIFT:
        return "drift"
    if value >= PSI_WARNING:
        return "warning"
    return "stable"


def feature_psi(spec, column):
    if spec["type"] == "binaire":
        p1 = float(column.mean())
        return psi([1 - spec["p1"], spec["p1"]], [1 - p1, p1])
    edges = np.array(spec["edges"])
    counts = np.bincount(np.digitize(column, edges), minlength=len(edges) + 1)
    return psi(spec["proportions"], counts / len(column))


def compute_drift(reference, X, feature_names):
    features = {}
    for j, name in enumerate(feature_names):
        value = round(feature_psi(reference[name], X[:, j]), 4)
        features[name] = {"psi": value, "status": status_of(value)}
    worst = max(features.values(), key=lambda item: item["psi"])
    return {
        "status": max((f["status"] for f in features.values()), key=RANK.get),
        "max_psi": worst["psi"],
        "features": features,
        "thresholds": {"warning": PSI_WARNING, "drift": PSI_DRIFT},
    }


def simulate_shift(X, feature_names, seed=42):
    """Données décalées pour la démonstration : budgets serrés, stocks bas."""
    rng = np.random.default_rng(seed)
    shifted = X.copy()
    budget = feature_names.index("budget_score")
    stock = feature_names.index("availability")
    shifted[:, budget] = np.clip(shifted[:, budget] * 0.4, 0, 1)
    shifted[:, stock] = (rng.random(len(shifted)) > 0.6).astype(float)
    return shifted


def main():
    from beauty_ml.data import CONTENT_FEATURES, design_matrix, load_split
    from beauty_ml.registry import load_active

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--simulate", action="store_true", help="décale les données")
    parser.add_argument("--report", default=str(REPORT_PATH))
    args = parser.parse_args()

    active = load_active()
    if not active or "reference" not in active:
        print("Aucun modèle actif avec référence : lancez d'abord retrain/retrain.py.")
        return 2
    train_rows, test_rows = load_split()
    X = design_matrix(train_rows + test_rows)
    if args.simulate:
        X = simulate_shift(X, CONTENT_FEATURES)
    result = compute_drift(active["reference"], X, CONTENT_FEATURES)
    result.update({"model_version": active["version"], "simulated": args.simulate, "rows": len(X)})

    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Dérive des données vs modèle {active['version']}"
          f"{' (données simulées)' if args.simulate else ''} : {result['status'].upper()}")
    for name, item in result["features"].items():
        print(f"  {name:<14} PSI {item['psi']:<7} {item['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
