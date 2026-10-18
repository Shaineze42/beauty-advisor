"""Chargement des données d'apprentissage et matrice de caractéristiques."""
import csv
import hashlib
from pathlib import Path

import numpy as np

from beauty_ml.bridge import engine

TRAIN_PATH = Path("data/processed/train.csv")
TEST_PATH = Path("data/processed/test.csv")

# Caractéristiques de contenu : apprises. Les deux signaux contextuels
# (interaction, historique) sont calculés à partir des labels : les apprendre
# sur les mêmes labels reviendrait à leur donner la réponse (fuite de cible).
CONTENT_FEATURES = ["skin_match", "finish_match", "budget_score", "availability"]
FIXED_FEATURES = ["interaction", "history_match"]


def read_csv(path):
    with Path(path).open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def design_matrix(rows):
    """Quatre caractéristiques de contenu, calculées comme dans le moteur."""
    return np.array(
        [
            [
                engine.to_int(row.get("skin_match")),
                engine.to_int(row.get("finish_match")),
                engine.budget_score_of(row),
                engine.to_int(row.get("available_flag")),
            ]
            for row in rows
        ],
        dtype=float,
    )


def labels(rows):
    return np.array([int(row["label"]) for row in rows])


def load_split(train_path=TRAIN_PATH, test_path=TEST_PATH):
    train_rows = read_csv(train_path)
    test_rows = read_csv(test_path)
    return train_rows, test_rows


def data_hash(train_path=TRAIN_PATH, test_path=TEST_PATH):
    digest = hashlib.sha256()
    for path in (train_path, test_path):
        digest.update(Path(path).read_bytes())
    return digest.hexdigest()
