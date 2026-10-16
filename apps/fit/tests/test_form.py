"""team_form snapshot: counts, season and last-10 means, coverage of every active team (Stage 4)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from footy.alerts import raise_alert
from footy.form.snapshot import build_team_form, current_season
from footy.models.types import TrainingMatch
from footy.repo.ops import OpsRepo
from tests.helpers import SqliteD1

AS_OF = date(2026, 10, 17)


def match(
    day: date, home: int, away: int, gh: int, ga: int, season: str = "2026-27"
) -> TrainingMatch:
    return TrainingMatch(
        comp_code="EPL",
        goals_home=gh,
        goals_away=ga,
        match_date=day,
        home_id=home,
        away_id=away,
        season=season,
    )


def test_hand_computed_form() -> None:
    d = [AS_OF - timedelta(days=k) for k in (40, 30, 20, 10)]
    matches = [
        match(d[0], 1, 2, 2, 0, "2025-26"),  # last season
        match(d[1], 2, 1, 1, 3),  # team 1 away: 3 for, 1 against
        match(d[2], 1, 3, 0, 0),
        match(d[3], 4, 1, 2, 2),
    ]
    forms = {f.team_id: f for f in build_team_form(matches, [1, 2, 3, 4], AS_OF, 1095)}
    f1 = forms[1]
    assert f1.n_training == 4 and f1.n_season == 3
    assert f1.season_gf == pytest.approx((3 + 0 + 2) / 3)
    assert f1.season_ga == pytest.approx((1 + 0 + 2) / 3)
    assert f1.l10_n == 4
    assert f1.l10_gf == pytest.approx((2 + 3 + 0 + 2) / 4)
    assert f1.l10_ga == pytest.approx((0 + 1 + 0 + 2) / 4)
    assert f1.latest_match_date == d[3].isoformat()
    assert forms[3].n_training == 1 and forms[3].season_gf == 0.0


def test_last_ten_uses_only_the_ten_most_recent_matches() -> None:
    matches = [match(AS_OF - timedelta(days=60 - 3 * k), 1, 2, k, 0) for k in range(15)]
    f = {f.team_id: f for f in build_team_form(matches, [1, 2], AS_OF, 1095)}[1]
    assert f.n_training == 15 and f.l10_n == 10
    assert f.l10_gf == pytest.approx(sum(range(5, 15)) / 10)


def test_every_active_team_gets_a_row_even_without_matches() -> None:
    forms = build_team_form(
        [match(AS_OF - timedelta(days=5), 1, 2, 1, 1)], [1, 2, 3, 9], AS_OF, 1095
    )
    by_id = {f.team_id: f for f in forms}
    assert set(by_id) == {1, 2, 3, 9}
    empty = by_id[9]
    assert (empty.n_training, empty.n_season, empty.l10_n) == (0, 0, 0)
    assert empty.season_gf is None and empty.l10_ga is None and empty.latest_match_date is None


def test_teams_with_matches_but_not_listed_are_included_and_order_is_by_id() -> None:
    forms = build_team_form([match(AS_OF - timedelta(days=5), 8, 3, 1, 0)], [5], AS_OF, 1095)
    assert [f.team_id for f in forms] == [3, 5, 8]


def test_matches_outside_the_window_do_not_count() -> None:
    old = match(AS_OF - timedelta(days=2000), 1, 2, 5, 0)
    recent = match(AS_OF - timedelta(days=3), 1, 2, 1, 0)
    f = {f.team_id: f for f in build_team_form([old, recent], [1], AS_OF, 1095)}[1]
    assert f.n_training == 1


def test_no_matches_at_all() -> None:
    assert current_season([]) is None
    forms = build_team_form([], [1, 2], AS_OF, 1095)
    assert [f.n_training for f in forms] == [0, 0]


def test_the_season_is_the_one_of_the_latest_match() -> None:
    matches = [
        match(AS_OF - timedelta(days=100), 1, 2, 1, 0, "2025-26"),
        match(AS_OF - timedelta(days=1), 1, 2, 2, 0),
    ]
    assert current_season(matches) == "2026-27"


def test_alert_stub_dedupes_per_key_for_24_hours() -> None:
    db = SqliteD1()
    ops = OpsRepo(db)
    assert raise_alert(ops, "2026-10-17T01:00:00Z", "run:R1", "run_rejected", {"why": "x"}) is True
    assert raise_alert(ops, "2026-10-17T05:00:00Z", "run:R1", "run_rejected", {"why": "x"}) is False
    assert raise_alert(ops, "2026-10-17T05:00:00Z", "run:R2", "run_rejected", {"why": "y"}) is True
    assert raise_alert(ops, "2026-10-18T02:00:00Z", "run:R1", "run_rejected", {"why": "x"}) is True
    rows = db.rows("SELECT level, source, kind, dedupe_key FROM events ORDER BY event_id")
    assert [r["dedupe_key"] for r in rows] == ["alert:run:R1", "alert:run:R2", "alert:run:R1"]
    assert rows[0]["level"] == "alert"
