"""History rule and goals drift (architecture section 8.4, ADR-021, ADR-044), hand-computed."""

from __future__ import annotations

import pytest

from footy.drift import (
    DRIFT,
    INSUFFICIENT_HISTORY,
    OK,
    assess_fixture,
    assess_team,
)
from footy.form.snapshot import TeamForm


def form(
    team_id: int = 1,
    *,
    n_training: int = 40,
    n_season: int = 12,
    season_gf: float | None = 1.5,
    season_ga: float | None = 1.0,
    l10_n: int = 10,
    l10_gf: float | None = 1.5,
    l10_ga: float | None = 1.0,
) -> TeamForm:
    return TeamForm(team_id, n_training, n_season, season_gf, season_ga, l10_n, l10_gf, l10_ga, "d")


def test_a_stable_team_is_ok_and_carries_its_statistics() -> None:
    a = assess_team(1, form(l10_gf=1.8, l10_ga=0.7))
    assert a.status == OK
    assert a.stats["d_gf"] == pytest.approx(0.3)
    assert a.stats["d_ga"] == pytest.approx(0.3)
    assert a.stats["threshold"] == 0.6


def test_goals_for_beyond_the_threshold_is_drift_and_names_the_check() -> None:
    a = assess_team(1, form(l10_gf=2.2))  # +0.7
    assert (a.status, a.reason) == (DRIFT, "goals_for")


def test_goals_against_beyond_the_threshold_is_drift() -> None:
    a = assess_team(1, form(l10_ga=0.3))  # -0.7
    assert (a.status, a.reason) == (DRIFT, "goals_against")


def test_both_checks_failing_are_both_named() -> None:
    a = assess_team(1, form(l10_gf=2.4, l10_ga=0.2))
    assert (a.status, a.reason) == (DRIFT, "goals_for+goals_against")


def test_a_difference_of_exactly_the_threshold_passes_despite_float_noise() -> None:
    # 1.8 - 1.2 is 0.6000000000000001 in floating point; the boundary must still pass.
    assert assess_team(1, form(season_gf=1.2, l10_gf=1.8)).status == OK
    assert assess_team(1, form(season_gf=1.2, l10_gf=1.8001)).status == DRIFT


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"n_training": 9}, "few_training_matches"),
        ({"l10_n": 9}, "few_recent_matches"),
        ({"season_gf": None, "season_ga": None, "n_season": 0}, "no_season_matches"),
        ({"l10_gf": None}, "no_season_matches"),
    ],
)
def test_too_little_history_is_insufficient_history(kwargs: dict[str, object], reason: str) -> None:
    a = assess_team(1, form(**kwargs))  # type: ignore[arg-type]
    assert (a.status, a.reason) == (INSUFFICIENT_HISTORY, reason)


def test_exactly_ten_matches_is_enough() -> None:
    assert assess_team(1, form(n_training=10, l10_n=10)).status == OK


def test_a_team_without_a_form_row_is_insufficient_history() -> None:
    a = assess_team(7, None)
    assert (a.status, a.reason) == (INSUFFICIENT_HISTORY, "no_form_row")


def test_a_fixture_is_stable_only_when_both_teams_are() -> None:
    forms = {1: form(1), 2: form(2)}
    assert assess_fixture(1, 2, forms).verdict == OK
    forms[2] = form(2, l10_gf=2.5)
    assert assess_fixture(1, 2, forms).verdict == DRIFT


def test_insufficient_history_wins_over_drift() -> None:
    forms = {1: form(1, n_training=3), 2: form(2, l10_gf=2.5)}
    result = assess_fixture(1, 2, forms)
    assert result.verdict == INSUFFICIENT_HISTORY
    assert result.home.status == INSUFFICIENT_HISTORY and result.away.status == DRIFT


def test_the_threshold_and_minimum_are_parameters() -> None:
    forms = {1: form(1, l10_gf=2.2), 2: form(2)}
    assert assess_fixture(1, 2, forms, threshold=0.8).verdict == OK
    assert assess_fixture(1, 2, forms, min_matches=50).verdict == INSUFFICIENT_HISTORY


def test_the_assessment_serialises_for_detail_json() -> None:
    d = assess_fixture(1, 2, {1: form(1), 2: form(2)}).as_dict()
    assert d["verdict"] == OK
    assert d["home"]["team_id"] == 1 and d["away"]["status"] == OK  # type: ignore[index]
