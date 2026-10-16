"""Ensemble weights: hand-computed values, shrinkage and edge cases (Stage 4)."""

from __future__ import annotations

import math

import pytest

from footy.ensemble.weights import (
    METHOD_BACKTEST,
    METHOD_EQUAL,
    METHOD_ROLLING,
    ensemble_weights,
    equal_weights,
    mean_recent_rps,
    prior_from_backtest,
    softmax_weights,
)

W1 = 1.0 / (1.0 + math.exp(-1.0))  # 0.7310586: exp(-20) against exp(-21)


def test_softmax_hand_computed() -> None:
    w = softmax_weights({"a": 0.20, "b": 0.21}, kappa=100.0)
    assert w["a"] == pytest.approx(W1)
    assert w["b"] == pytest.approx(1.0 - W1)
    assert w["a"] == pytest.approx(0.7310586, abs=1e-7)


def test_softmax_kappa_zero_gives_equal_weights_and_is_stable_for_large_values() -> None:
    assert softmax_weights({"a": 0.1, "b": 0.9}, kappa=0.0) == {"a": 0.5, "b": 0.5}
    big = softmax_weights({"a": 0.2, "b": 0.5}, kappa=1e6)  # exp(-3e5) must not underflow to 0/0
    assert big["a"] == pytest.approx(1.0) and big["b"] == pytest.approx(0.0)


def test_equal_weights() -> None:
    assert equal_weights(["dc", "pi", "bp"]) == pytest.approx(
        {"dc": 1 / 3, "pi": 1 / 3, "bp": 1 / 3}
    )


def test_no_information_gives_equal_weights() -> None:
    w = ensemble_weights(["dc", "pi", "bp"])
    assert w.method == METHOD_EQUAL and w.n_scored == 0
    assert sum(w.weights.values()) == pytest.approx(1.0)
    assert w.weights["pi"] == pytest.approx(1 / 3)


def test_backtest_prior_is_used_until_predictions_are_scored() -> None:
    w = ensemble_weights(["a", "b"], prior_rps={"a": 0.20, "b": 0.21})
    assert w.method == METHOD_BACKTEST and w.n_scored == 0
    assert w.weights["a"] == pytest.approx(W1)


def test_shrinkage_hand_computed() -> None:
    history = {"a": [0.20] * 50, "b": [0.21] * 50}
    # n = 50 and shrink_n = 50: half the rolling softmax, half equal weights
    w = ensemble_weights(["a", "b"], history=history)
    assert w.method == METHOD_ROLLING and w.n_scored == 50
    assert w.weights["a"] == pytest.approx(0.5 * W1 + 0.5 * 0.5)  # 0.6155293
    assert w.weights["a"] == pytest.approx(0.6155293, abs=1e-7)
    # n = 150: three quarters rolling
    long = ensemble_weights(["a", "b"], history={"a": [0.20] * 150, "b": [0.21] * 150})
    assert long.weights["a"] == pytest.approx(0.75 * W1 + 0.25 * 0.5)
    # n = 1 is almost all prior
    one = ensemble_weights(["a", "b"], history={"a": [0.0], "b": [1.0]})
    assert one.weights["a"] == pytest.approx(0.5, abs=0.02)


def test_scored_history_shrinks_toward_the_backtest_prior_when_there_is_one() -> None:
    prior = {"a": 0.20, "b": 0.21}
    w = ensemble_weights(["a", "b"], history={"a": [0.3] * 50, "b": [0.3] * 50}, prior_rps=prior)
    # rolling RPS are equal -> w_rps is 0.5/0.5; half the weight comes from the backtest prior
    assert w.weights["a"] == pytest.approx(0.5 * 0.5 + 0.5 * W1)


def test_only_the_most_recent_predictions_count() -> None:
    history = {"a": [1.0] * 100 + [0.2] * 200, "b": [0.0] * 100 + [0.21] * 200}
    w = ensemble_weights(["a", "b"], history=history, recent=200)
    assert w.n_scored == 200
    keep = 200 / 250
    assert w.weights["a"] == pytest.approx(keep * W1 + (1 - keep) * 0.5)
    assert mean_recent_rps(history, recent=200) == pytest.approx({"a": 0.2, "b": 0.21})


def test_a_failed_model_is_left_out_and_weights_still_sum_to_one() -> None:
    w = ensemble_weights(["dc", "bp"], prior_rps={"dc": 0.2, "pi": 0.1, "bp": 0.2})
    assert set(w.weights) == {"dc", "bp"}
    assert sum(w.weights.values()) == pytest.approx(1.0)
    assert w.weights["dc"] == pytest.approx(0.5)


def test_a_model_without_history_falls_back_to_the_prior() -> None:
    w = ensemble_weights(["a", "b"], history={"a": [0.2] * 80})
    assert w.method == METHOD_EQUAL and w.n_scored == 0


def test_a_prior_that_misses_a_model_is_ignored() -> None:
    w = ensemble_weights(["a", "b"], prior_rps={"a": 0.2})
    assert w.method == METHOD_EQUAL


def test_misaligned_histories_use_the_shorter_length() -> None:
    w = ensemble_weights(["a", "b"], history={"a": [0.2] * 70, "b": [0.2] * 40})
    assert w.n_scored == 40


@pytest.mark.parametrize("bad", [{}, {"a": float("nan")}, {"a": -0.1}])
def test_softmax_rejects_bad_input(bad: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        softmax_weights(bad)


def test_other_invalid_arguments() -> None:
    with pytest.raises(ValueError):
        softmax_weights({"a": 0.1}, kappa=-1.0)
    with pytest.raises(ValueError):
        ensemble_weights([])
    with pytest.raises(ValueError):
        equal_weights([])


def test_prior_from_a_stored_backtest_summary() -> None:
    summary = {
        "result": {
            "models": {
                "dc": {"overall": {"rps_1x2": 0.19}},
                "pi": {"overall": {"rps_1x2": 0.2}},
            }
        }
    }
    assert prior_from_backtest(summary, ["dc", "pi"]) == {"dc": 0.19, "pi": 0.2}
    assert prior_from_backtest(summary, ["dc", "bp"]) == {}  # one model is missing -> unusable
    assert prior_from_backtest(None, ["dc"]) == {}
    assert prior_from_backtest({"result": "nope"}, ["dc"]) == {}
    assert prior_from_backtest({"result": {"models": {"dc": {"overall": None}}}}, ["dc"]) == {}


def test_as_dict_carries_the_settings_used() -> None:
    d = ensemble_weights(["a", "b"]).as_dict()
    assert d["method"] == METHOD_EQUAL and d["kappa"] == 100.0 and d["shrink_n"] == 50
