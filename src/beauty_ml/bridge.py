"""Lien avec le moteur de recommandation (dossier app/).

Le moteur reste la source de vérité du score : on ne le recopie pas, on le
pilote (changement temporaire des poids, évaluation hors ligne).
Tous les scripts se lancent depuis la racine du dépôt.
"""
import contextlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_DIR = ROOT / "app"
# En dernier : app/ contient un ancien api.py qui ne doit pas masquer le paquet api/.
if str(APP_DIR) not in sys.path:
    sys.path.append(str(APP_DIR))

import evaluate_personalized as evaluation  # noqa: E402
import recommendation_engine as engine  # noqa: E402


@contextlib.contextmanager
def use_weights(weights):
    """Applique des poids au moteur le temps d'un bloc, puis restaure."""
    saved = dict(engine.SCORE_WEIGHTS)
    engine.SCORE_WEIGHTS.update(weights)
    try:
        yield
    finally:
        engine.SCORE_WEIGHTS.clear()
        engine.SCORE_WEIGHTS.update(saved)


def run_offline_evaluation(weights, report_path):
    """Lance l'évaluation personnalisée du moteur avec ces poids.

    Réutilise evaluate_personalized.main() sans toucher au rapport officiel.
    """
    previous = evaluation.REPORT_PATH
    evaluation.REPORT_PATH = Path(report_path)
    try:
        with use_weights(weights), contextlib.redirect_stdout(io.StringIO()):
            evaluation.main()
    finally:
        evaluation.REPORT_PATH = previous
    with Path(report_path).open("r", encoding="utf-8") as file:
        return json.load(file)
