"""History rule and goals drift check (architecture section 8.4, ADR-021, ADR-026, ADR-044).

Evaluated once, here, when the nightly forecast is made; the Worker only shows the stored verdict.
Pure functions over the run's own ``team_form`` rows.

Per team, in this order:

* ``INSUFFICIENT_HISTORY``: no ``team_form`` row, fewer than ``min_matches`` training matches,
  fewer than ``min_matches`` matches in the last-10 window, or no match in the current season
  (its season average is undefined);
* ``DRIFT``: ``max(|l10_gf - season_gf|, |l10_ga - season_ga|)`` is above the threshold;
* otherwise stable.

A fixture is stable only when both teams are. When one team fails the history rule and the other
drifts, ``INSUFFICIENT_HISTORY`` is reported (the drift number would rest on too little data).
The comparison uses a small tolerance so a difference of exactly the threshold passes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from footy.config import DRIFT_THRESHOLD_GOALS, DRIFT_TOLERANCE, MIN_TEAM_MATCHES
from footy.form.snapshot import TeamForm

OK = "ok"
INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
DRIFT = "DRIFT"


@dataclass(frozen=True)
class TeamAssessment:
    team_id: int
    status: str  # OK, INSUFFICIENT_HISTORY or DRIFT
    reason: str | None = None
    stats: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        out: dict[str, object] = {"team_id": self.team_id, "status": self.status, **self.stats}
        if self.reason is not None:
            out["reason"] = self.reason
        return out


@dataclass(frozen=True)
class FixtureAssessment:
    verdict: str  # OK, INSUFFICIENT_HISTORY or DRIFT
    home: TeamAssessment
    away: TeamAssessment

    def as_dict(self) -> dict[str, object]:
        return {"verdict": self.verdict, "home": self.home.as_dict(), "away": self.away.as_dict()}


def assess_team(
    team_id: int,
    form: TeamForm | None,
    *,
    threshold: float = DRIFT_THRESHOLD_GOALS,
    min_matches: int = MIN_TEAM_MATCHES,
) -> TeamAssessment:
    if form is None:
        return TeamAssessment(team_id, INSUFFICIENT_HISTORY, "no_form_row")
    counts: dict[str, object] = {"n_training": form.n_training, "l10_n": form.l10_n}
    if form.n_training < min_matches:
        return TeamAssessment(team_id, INSUFFICIENT_HISTORY, "few_training_matches", counts)
    if form.l10_n < min_matches:
        return TeamAssessment(team_id, INSUFFICIENT_HISTORY, "few_recent_matches", counts)
    if (
        form.season_gf is None
        or form.season_ga is None
        or form.l10_gf is None
        or form.l10_ga is None
    ):
        return TeamAssessment(team_id, INSUFFICIENT_HISTORY, "no_season_matches", counts)
    d_gf = abs(form.l10_gf - form.season_gf)
    d_ga = abs(form.l10_ga - form.season_ga)
    stats: dict[str, object] = {
        **counts,
        "season_gf": form.season_gf,
        "season_ga": form.season_ga,
        "l10_gf": form.l10_gf,
        "l10_ga": form.l10_ga,
        "d_gf": d_gf,
        "d_ga": d_ga,
        "threshold": threshold,
    }
    if max(d_gf, d_ga) > threshold + DRIFT_TOLERANCE:
        failed = [
            name
            for name, d in (("goals_for", d_gf), ("goals_against", d_ga))
            if d > threshold + DRIFT_TOLERANCE
        ]
        return TeamAssessment(team_id, DRIFT, "+".join(failed), stats)
    return TeamAssessment(team_id, OK, None, stats)


def assess_fixture(
    home_id: int,
    away_id: int,
    forms: Mapping[int, TeamForm],
    *,
    threshold: float = DRIFT_THRESHOLD_GOALS,
    min_matches: int = MIN_TEAM_MATCHES,
) -> FixtureAssessment:
    home = assess_team(home_id, forms.get(home_id), threshold=threshold, min_matches=min_matches)
    away = assess_team(away_id, forms.get(away_id), threshold=threshold, min_matches=min_matches)
    statuses = {home.status, away.status}
    if INSUFFICIENT_HISTORY in statuses:
        verdict = INSUFFICIENT_HISTORY
    elif DRIFT in statuses:
        verdict = DRIFT
    else:
        verdict = OK
    return FixtureAssessment(verdict, home, away)
