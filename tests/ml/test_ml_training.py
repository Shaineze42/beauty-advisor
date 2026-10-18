import numpy as np
import pytest

from beauty_ml.data import CONTENT_FEATURES, FIXED_FEATURES
from beauty_ml.training import (
    C_GRID,
    choose_regularisation,
    coefficients_to_weights,
    content_auc,
    fit_candidate,
)

FIXED = {"interaction": 0.15, "history_match": 0.10}


def synthetic(n=300, seed=0):
    """La peau compte beaucoup, le fini un peu, le reste pas du tout."""
    rng = np.random.default_rng(seed)
    X = np.column_stack(
        [
            rng.integers(0, 2, n),
            rng.integers(0, 2, n),
            rng.random(n),
            rng.integers(0, 2, n),
        ]
    ).astype(float)
    logit = 3.0 * X[:, 0] + 1.0 * X[:, 1] - 2.0
    y = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    groups = [f"user_{i % 20}" for i in range(n)]
    return X, y, groups


def test_weights_sum_to_one_and_keep_fixed_part():
    weights = coefficients_to_weights([1.0, 2.0, 0.5, 0.25], FIXED)
    assert set(weights) == set(CONTENT_FEATURES + FIXED_FEATURES)
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert weights["interaction"] == 0.15 and weights["history_match"] == 0.10


def test_negative_coefficients_are_clipped_to_zero():
    weights = coefficients_to_weights([2.0, -1.0, 1.0, 0.0], FIXED)
    assert weights["finish_match"] == 0.0
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_all_non_positive_coefficients_are_refused():
    with pytest.raises(ValueError):
        coefficients_to_weights([-1.0, 0.0, -0.5, 0.0], FIXED)


def test_learning_finds_the_informative_feature():
    X, y, groups = synthetic()
    candidate = fit_candidate(X, y, groups, FIXED)
    weights = candidate["weights"]
    assert weights["skin_match"] > weights["finish_match"] > weights["availability"]
    assert candidate["learned"]["C"] in C_GRID
    assert content_auc(weights, X, y) > 0.7


def test_regularisation_is_chosen_from_the_grid():
    X, y, groups = synthetic()
    best_c, auc, scores = choose_regularisation(X, y, groups)
    assert best_c in C_GRID
    assert 0.5 < auc <= 1.0
    assert set(scores) == {str(c) for c in C_GRID}
