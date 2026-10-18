import numpy as np

from monitoring.drift import (
    build_reference,
    compute_drift,
    psi,
    simulate_shift,
    status_of,
)

NAMES = ["skin_match", "finish_match", "budget_score", "availability"]


def sample(n=400, seed=1):
    rng = np.random.default_rng(seed)
    return np.column_stack(
        [
            rng.integers(0, 2, n),
            rng.integers(0, 2, n),
            rng.random(n),
            (rng.random(n) < 0.8).astype(int),
        ]
    ).astype(float)


def test_psi_is_zero_for_identical_distributions():
    assert psi([0.5, 0.5], [0.5, 0.5]) == 0.0


def test_status_thresholds():
    assert status_of(0.05) == "stable"
    assert status_of(0.10) == "warning"
    assert status_of(0.24) == "warning"
    assert status_of(0.25) == "drift"


def test_same_data_is_stable():
    X = sample()
    result = compute_drift(build_reference(X, NAMES), X, NAMES)
    assert result["status"] == "stable"
    assert result["max_psi"] < 0.01


def test_new_sample_of_same_law_stays_stable():
    reference = build_reference(sample(seed=1), NAMES)
    result = compute_drift(reference, sample(seed=2), NAMES)
    assert result["status"] == "stable"


def test_simulated_shift_is_detected_on_the_shifted_features_only():
    X = sample()
    result = compute_drift(build_reference(X, NAMES), simulate_shift(X, NAMES), NAMES)
    assert result["status"] == "drift"
    assert result["features"]["budget_score"]["status"] == "drift"
    assert result["features"]["availability"]["status"] == "drift"
    assert result["features"]["skin_match"]["status"] == "stable"


def test_constant_column_does_not_crash():
    X = sample()
    X[:, 2] = 0.5
    result = compute_drift(build_reference(X, NAMES), X, NAMES)
    assert result["features"]["budget_score"]["psi"] == 0.0
