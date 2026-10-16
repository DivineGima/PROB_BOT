"""Scoring rules, baseline and calibration with hand-computed answers (Stage 3)."""

from __future__ import annotations

import math

import pytest

from footy.models.grid import OVER_LINES, TOTAL_CATEGORIES, Markets
from footy.scoring import (
    FrequencyBaseline,
    Result,
    brier_over,
    calibration_bins,
    log_loss_1x2,
    mean_scores,
    outcome_1x2,
    rps,
    rps_1x2,
    rps_totals,
    score_forecast,
    total_category,
)


def test_outcome_and_total_category() -> None:
    assert [outcome_1x2(2, 1), outcome_1x2(1, 1), outcome_1x2(0, 3)] == [0, 1, 2]
    assert total_category(0, 0) == 0
    assert total_category(5, 6) == 11
    assert total_category(7, 5) == 12
    assert total_category(10, 10) == 12


def test_rps_hand_computed_for_each_outcome() -> None:
    # forecast H 0.5 D 0.3 A 0.2; cumulative forecast 0.5, 0.8
    assert rps_1x2(0.5, 0.3, 0.2, 2, 0) == pytest.approx((0.5**2 + 0.2**2) / 2)  # home won
    assert rps_1x2(0.5, 0.3, 0.2, 1, 1) == pytest.approx((0.5**2 + 0.2**2) / 2)  # draw
    assert rps_1x2(0.5, 0.3, 0.2, 0, 1) == pytest.approx((0.5**2 + 0.8**2) / 2)  # away won


def test_rps_extremes_and_ordering() -> None:
    assert rps_1x2(1.0, 0.0, 0.0, 1, 0) == 0.0
    assert rps_1x2(0.0, 0.0, 1.0, 1, 0) == 1.0
    # a near miss (draw forecast, home win) is penalised less than a far miss (away forecast)
    assert rps_1x2(0.0, 1.0, 0.0, 1, 0) < rps_1x2(0.0, 0.0, 1.0, 1, 0)


def test_rps_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        rps([1.0], 0)
    with pytest.raises(ValueError):
        rps([0.5, 0.5], 2)


def test_rps_totals_uses_thirteen_ordered_categories() -> None:
    pmf = [0.0] * TOTAL_CATEGORIES
    pmf[2] = 1.0
    assert rps_totals(pmf, 1, 1) == 0.0  # exactly two goals
    # forecast says 2 goals, three happened: one cumulative step of 1.0 out of 12 terms
    assert rps_totals(pmf, 2, 1) == pytest.approx(1.0 / 12)
    # twelve or more goals all land in the last category
    assert rps_totals(pmf, 9, 9) == pytest.approx(10 / 12)
    with pytest.raises(ValueError):
        rps_totals([1.0, 0.0], 0, 0)


def test_log_loss_and_floor() -> None:
    assert log_loss_1x2(0.5, 0.3, 0.2, 1, 0) == pytest.approx(-math.log(0.5))
    assert log_loss_1x2(1.0, 0.0, 0.0, 0, 1) == pytest.approx(-math.log(1e-15))  # finite, not inf


def test_brier_over_per_line() -> None:
    assert brier_over(0.7, 2, 1, 2.5) == pytest.approx(0.3**2)  # three goals: over 2.5 happened
    assert brier_over(0.7, 2, 1, 3.5) == pytest.approx(0.7**2)  # over 3.5 did not


def _forecast() -> Markets:
    pmf = [0.0] * TOTAL_CATEGORIES
    pmf[3] = 1.0
    return Markets(0.6, 0.3, 0.1, (1.0, 0.9, 0.8, 0.5, 0.2, 0.1), tuple(pmf))


def test_score_forecast_and_mean() -> None:
    scored = score_forecast(_forecast(), 2, 1)
    assert scored.rps_1x2 == pytest.approx(((0.6 - 1) ** 2 + (0.9 - 1) ** 2) / 2)
    assert scored.rps_totals == 0.0
    assert scored.logloss_1x2 == pytest.approx(-math.log(0.6))
    assert len(scored.brier_overs) == len(OVER_LINES)
    mean = mean_scores([scored, score_forecast(_forecast(), 0, 0)])
    assert mean.n == 2
    assert mean.rps_1x2 == pytest.approx(
        (scored.rps_1x2 + score_forecast(_forecast(), 0, 0).rps_1x2) / 2
    )
    assert mean.as_dict()["n"] == 2
    with pytest.raises(ValueError):
        mean_scores([])


def _results(comp: str, wins: int, draws: int, losses: int) -> list[Result]:
    return (
        [Result(comp, 2, 0)] * wins + [Result(comp, 1, 1)] * draws + [Result(comp, 0, 3)] * losses
    )


def test_baseline_frequencies_per_competition() -> None:
    results = _results("EPL", 20, 10, 20) + _results("LL", 30, 15, 5)
    baseline = FrequencyBaseline.from_results(results, min_matches=30)
    epl = baseline.forecast("EPL")
    assert (epl.p_home, epl.p_draw, epl.p_away) == pytest.approx((0.4, 0.2, 0.4))
    # EPL totals: 2 goals x20, 2 goals x10 (1-1), 3 goals x20 -> over 2.5 is 20/50
    assert epl.overs[2] == pytest.approx(0.4)
    assert sum(epl.total_pmf) == pytest.approx(1.0)
    assert baseline.n == 100


def test_baseline_falls_back_to_pooled_for_small_or_unknown_competitions() -> None:
    results = _results("EPL", 30, 0, 0) + _results("SPL", 1, 1, 1)
    baseline = FrequencyBaseline.from_results(results, min_matches=30)
    pooled = baseline.forecast("SPL")
    assert baseline.forecast("UNKNOWN") == pooled
    assert pooled.p_home == pytest.approx(31 / 33)
    snapshot = baseline.snapshot()
    assert snapshot["n"] == 33
    frequencies = snapshot["frequencies"]
    assert isinstance(frequencies, dict)
    assert set(frequencies) == {"*", "EPL"}


def test_baseline_needs_data() -> None:
    with pytest.raises(ValueError):
        FrequencyBaseline.from_results([])


def test_calibration_bins() -> None:
    pairs = [(0.05, False), (0.05, False), (0.15, True), (0.95, True), (1.0, True), (0.0, False)]
    bins = calibration_bins(pairs, n_bins=10)
    by_low = {round(b.low, 1): b for b in bins}
    assert by_low[0.0].n == 3
    assert by_low[0.0].observed_frequency == 0.0
    assert by_low[0.0].mean_forecast == pytest.approx(0.1 / 3)
    assert by_low[0.1].observed_frequency == 1.0
    assert by_low[0.9].n == 2  # 0.95 and exactly 1.0 share the last bin
    assert 0.5 not in by_low  # empty bins are omitted
    assert by_low[0.9].as_dict()["n"] == 2


def test_calibration_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        calibration_bins([(1.2, True)])
    with pytest.raises(ValueError):
        calibration_bins([], n_bins=0)
    assert calibration_bins([]) == []
