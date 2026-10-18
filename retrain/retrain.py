"""Réentraînement automatisé : déclencheurs, apprentissage, comparaison, promotion.

Étapes :
  1. déclencheurs : pas de modèle actif, données modifiées, dérive, ou --force
  2. apprentissage d'un candidat (régression logistique) sur le split d'entraînement
  3. évaluation du candidat ET du modèle actif sur le même jeu de test
  4. décision : promotion seulement si aucune règle métier n'est violée,
     sans baisse de précision, avec un gain d'AUC minimal
  5. enregistrement (versions/, registry.json) et rapport reports/retrain_report.json

Usage (depuis la racine du dépôt, après la préparation des données) :
  python retrain/retrain.py                  # exécution normale
  python retrain/retrain.py --force          # réentraîne même sans déclencheur
  python retrain/retrain.py --simulate-drift # démontre le déclencheur de dérive
  python retrain/retrain.py --dry-run        # n'écrit rien dans models/
  python retrain/retrain.py --rollback       # revient à la version précédente
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from beauty_ml import registry  # noqa: E402
from beauty_ml.bridge import engine  # noqa: E402
from beauty_ml.data import (  # noqa: E402
    CONTENT_FEATURES,
    FIXED_FEATURES,
    data_hash,
    design_matrix,
    labels,
    load_split,
)
from beauty_ml.evaluation import decide, evaluate  # noqa: E402
from beauty_ml.training import fit_candidate  # noqa: E402
from monitoring.drift import build_reference, compute_drift, simulate_shift  # noqa: E402

REPORT_PATH = Path("reports/retrain_report.json")


def say(message):
    print(message, flush=True)


def baseline_model(models_dir, X_train, X_test, y_test, digest, sizes):
    """Version 0 : les poids fixés à la main, évalués comme n'importe quel modèle."""
    weights = dict(engine.DEFAULT_SCORE_WEIGHTS)
    return {
        "version": registry.next_version(models_dir),
        "created_at": registry.now(),
        "origin": "poids fixés à la main (référence de départ)",
        "weights": weights,
        "learned": None,
        "data": {**sizes, "data_hash": digest},
        "metrics": evaluate(weights, X_test, y_test),
        "reference": build_reference(X_train, CONTENT_FEATURES),
    }


def write_report(report, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(args):
    models_dir = Path(args.models_dir)
    train_rows, test_rows = load_split()
    X_train, y_train = design_matrix(train_rows), labels(train_rows)
    X_test, y_test = design_matrix(test_rows), labels(test_rows)
    groups = [row["user_id"] for row in train_rows]
    digest = data_hash()
    sizes = {"train_rows": len(train_rows), "test_rows": len(test_rows)}
    write = not args.dry_run
    report = {"dry_run": args.dry_run, "data": {**sizes, "data_hash": digest}}

    # Modèle actif (ou création de la référence de départ).
    active = registry.load_active(models_dir)
    triggers = []
    if active is None:
        say("Aucun modèle actif : enregistrement de la référence de départ (poids manuels).")
        active = baseline_model(models_dir, X_train, X_test, y_test, digest, sizes)
        if write:
            registry.save_version(active, models_dir)
            registry.record(models_dir, active["version"], "promu",
                            "référence de départ", active["metrics"])
            registry.promote(active["version"], models_dir)
        triggers.append("pas de modèle actif")

    # 1. Déclencheurs.
    X_now = simulate_shift(design_matrix(train_rows + test_rows), CONTENT_FEATURES) \
        if args.simulate_drift else design_matrix(train_rows + test_rows)
    drift = compute_drift(active["reference"], X_now, CONTENT_FEATURES)
    report["drift"] = drift
    say(f"Dérive des données : {drift['status'].upper()} (PSI max {drift['max_psi']})")
    if drift["status"] == "drift":
        triggers.append("dérive des données")
    if active["data"].get("data_hash") != digest:
        triggers.append("données modifiées depuis l'entraînement du modèle actif")
    if args.force:
        triggers.append("demande explicite (--force)")
    report["triggers"] = triggers
    report["active_before"] = active["version"]

    if not triggers:
        say("Aucun déclencheur : le modèle actif est conservé.")
        report["decision"] = {"promote": False, "reason": "aucun déclencheur"}
        write_report(report, args.report)
        return 0
    say("Déclencheurs : " + " ; ".join(triggers))

    # 2. Candidat.
    fixed = {name: engine.DEFAULT_SCORE_WEIGHTS[name] for name in FIXED_FEATURES}
    fitted = fit_candidate(X_train, y_train, groups, fixed)
    candidate = {
        "version": registry.next_version(models_dir),
        "created_at": registry.now(),
        "origin": "régression logistique sur les caractéristiques de contenu",
        "weights": fitted["weights"],
        "learned": fitted["learned"],
        "data": {**sizes, "data_hash": digest},
        "reference": build_reference(X_train, CONTENT_FEATURES),
    }
    say(f"Candidat {candidate['version']} appris : {candidate['weights']}")

    # 3. Évaluation sur le même test.
    current_metrics = evaluate(active["weights"], X_test, y_test)
    candidate["metrics"] = evaluate(candidate["weights"], X_test, y_test)
    say(f"AUC de contenu (test) : actif {current_metrics['content_auc_test']} "
        f"| candidat {candidate['metrics']['content_auc_test']}")

    # 4. Décision.
    decision = decide(candidate["metrics"], current_metrics,
                      min_auc_gain=args.min_gain)
    report.update(
        {
            "candidate": candidate["version"],
            "candidate_weights": candidate["weights"],
            "active_metrics": current_metrics,
            "candidate_metrics": candidate["metrics"],
            "decision": decision,
        }
    )
    label = "PROMU" if decision["promote"] else "NON PROMU"
    say(f"Décision : {label} : {decision['reason']}")

    # 5. Enregistrement.
    if write:
        registry.save_version(candidate, models_dir)
        registry.record(models_dir, candidate["version"],
                        "promu" if decision["promote"] else "rejeté",
                        decision["reason"], candidate["metrics"])
        if decision["promote"]:
            registry.promote(candidate["version"], models_dir)
    report["active_after"] = candidate["version"] if decision["promote"] and write else active["version"]
    write_report(report, args.report)
    say(f"Modèle actif : {report['active_after']} | rapport : {args.report}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--simulate-drift", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--min-gain", type=float, default=0.01)
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--report", default=str(REPORT_PATH))
    args = parser.parse_args()

    if args.rollback:
        try:
            version = registry.rollback(args.models_dir)
        except ValueError as error:
            say(f"Retour arrière impossible : {error}")
            return 2
        say(f"Retour arrière effectué : modèle actif {version}")
        return 0
    try:
        return run(args)
    except FileNotFoundError as error:
        say(f"Données absentes ({error.filename}) : préparez-les d'abord "
            "(python app/prepare_ai_data.py).")
        return 2


if __name__ == "__main__":
    sys.exit(main())
