"""Apprentissage des poids du score : régression logistique.

Le modèle reste explicable : la régression logistique apprend l'importance de
quatre caractéristiques de contenu, puis les coefficients (bornés à zéro)
sont ramenés à la part du score qu'ils occupent. Les poids obtenus remplacent
les poids fixés à la main dans la même formule de score.
"""
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

from beauty_ml.data import CONTENT_FEATURES, FIXED_FEATURES

C_GRID = (0.1, 0.3, 1.0, 3.0, 10.0)


def coefficients_to_weights(coefficients, fixed):
    """Coefficients de contenu -> poids du score (somme égale à 1)."""
    positive = np.clip(np.asarray(coefficients, dtype=float), 0, None)
    if positive.sum() <= 0:
        raise ValueError("Aucun coefficient positif : poids non définissables.")
    content_total = 1.0 - sum(fixed.values())
    shares = positive / positive.sum() * content_total
    weights = {name: round(float(share), 4) for name, share in zip(CONTENT_FEATURES, shares)}
    # Corrige l'arrondi sur le poids le plus fort pour garantir une somme de 1.
    gap = round(1.0 - sum(weights.values()) - sum(fixed.values()), 4)
    biggest = max(CONTENT_FEATURES, key=lambda name: weights[name])
    weights[biggest] = round(weights[biggest] + gap, 4)
    weights.update(fixed)
    return {name: weights[name] for name in CONTENT_FEATURES + FIXED_FEATURES}


def content_auc(weights, X, y):
    """AUC du score de contenu (les 4 caractéristiques apprises)."""
    vector = np.array([weights[name] for name in CONTENT_FEATURES])
    return float(roc_auc_score(y, X @ vector))


def choose_regularisation(X, y, groups, c_grid=C_GRID, splits=5):
    """Choisit C par validation croisée groupée par utilisateur."""
    n_groups = len(set(groups))
    folds = GroupKFold(n_splits=max(2, min(splits, n_groups)))
    best_c, best_auc, scores = None, -1.0, {}
    for c in c_grid:
        aucs = []
        for fit_idx, val_idx in folds.split(X, y, groups):
            if len(set(y[fit_idx])) < 2 or len(set(y[val_idx])) < 2:
                continue
            model = LogisticRegression(C=c, max_iter=1000).fit(X[fit_idx], y[fit_idx])
            aucs.append(roc_auc_score(y[val_idx], model.predict_proba(X[val_idx])[:, 1]))
        mean_auc = float(np.mean(aucs)) if aucs else float("nan")
        scores[str(c)] = round(mean_auc, 4)
        if aucs and mean_auc > best_auc + 1e-9:
            best_c, best_auc = c, mean_auc
    if best_c is None:
        raise ValueError("Validation croisée impossible : données insuffisantes.")
    return best_c, best_auc, scores


def fit_candidate(X, y, groups, fixed):
    """Apprend un candidat : poids, coefficients bruts, réglage retenu."""
    best_c, cv_auc, cv_scores = choose_regularisation(X, y, groups)
    model = LogisticRegression(C=best_c, max_iter=1000).fit(X, y)
    coefficients = model.coef_[0]
    return {
        "weights": coefficients_to_weights(coefficients, fixed),
        "learned": {
            "algorithm": "regression_logistique",
            "C": best_c,
            "cv_auc_grouped_by_user": round(cv_auc, 4),
            "cv_scores_by_C": cv_scores,
            "coefficients": {
                name: round(float(value), 4)
                for name, value in zip(CONTENT_FEATURES, coefficients)
            },
            "intercept": round(float(model.intercept_[0]), 4),
        },
    }
