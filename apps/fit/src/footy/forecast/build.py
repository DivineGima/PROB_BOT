"""One forecast per scheduled fixture (architecture section 8.11, ADR-042). Pure functions.

For a fixture: the history/drift verdict (``footy.drift``); then every fitted model that knows
both teams builds its grid, the grids are pooled with the run's ensemble weights (renormalised over
the models that produced a grid) and every market derives from that one pooled grid (section 8.1).
The per-model markets are kept so the per-model RPS can be recomputed once the result is known.

Only a verdict-``ok`` forecast carries probabilities; the other verdicts say why the Worker must
omit the match. A model that cannot build the grid for one fixture is left out of that fixture and
named in ``detail_json``; it is never replaced by a guess.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from footy.config import DRIFT_THRESHOLD_GOALS, MIN_TEAM_MATCHES
from footy.drift import OK, assess_fixture
from footy.form.snapshot import TeamForm
from footy.models.grid import Grid, GridError, Markets, markets, mix_grids
from footy.models.types import GridModel
from footy.scoring.baseline import FrequencyBaseline

NO_MODEL = "NO_MODEL"

FORECAST_COLUMNS: tuple[str, ...] = (
    "run_id",
    "fixture_key",
    "comp_code",
    "match_date",
    "kickoff_utc",
    "home_team_id",
    "away_team_id",
    "verdict",
    "p_home",
    "p_draw",
    "p_away",
    "p_over_05",
    "p_over_15",
    "p_over_25",
    "p_over_35",
    "p_over_45",
    "p_over_55",
    "total_json",
    "models_json",
    "weights_json",
    "baseline_json",
    "detail_json",
    "created_at",
)


@dataclass(frozen=True)
class Fixture:
    """A scheduled match (``matches`` row with status SCHEDULED or TIMED)."""

    comp_code: str
    match_date: date
    kickoff_utc: str | None
    home_id: int
    away_id: int


def fixture_key(match_date: date | str, comp_code: str, home_id: int, away_id: int) -> str:
    """The bot's own identity for a match (section 8.7): ``date|comp|home_team_id|away_team_id``."""
    day = match_date.isoformat() if isinstance(match_date, date) else match_date
    return f"{day}|{comp_code}|{home_id}|{away_id}"


@dataclass(frozen=True)
class ForecastRow:
    fixture_key: str
    comp_code: str
    match_date: str
    kickoff_utc: str | None
    home_team_id: int
    away_team_id: int
    verdict: str
    ensemble: Markets | None
    total_json: str | None
    models_json: str | None
    weights_json: str | None
    baseline_json: str | None
    detail_json: str
    created_at: str

    def values(self, run_id: str) -> tuple[object, ...]:
        e = self.ensemble
        return (
            run_id,
            self.fixture_key,
            self.comp_code,
            self.match_date,
            self.kickoff_utc,
            self.home_team_id,
            self.away_team_id,
            self.verdict,
            e.p_home if e else None,
            e.p_draw if e else None,
            e.p_away if e else None,
            *(e.overs if e else (None,) * 6),
            self.total_json,
            self.models_json,
            self.weights_json,
            self.baseline_json,
            self.detail_json,
            self.created_at,
        )


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def renormalise(weights: Mapping[str, float], names: Sequence[str]) -> dict[str, float]:
    """The run's weights restricted to ``names`` and rescaled to sum to 1 (equal weights if the
    restricted weights are all zero or unusable)."""
    chosen = {n: max(float(weights.get(n, 0.0)), 0.0) for n in names}
    chosen = {n: w if math.isfinite(w) else 0.0 for n, w in chosen.items()}
    total = sum(chosen.values())
    if total <= 0.0:
        return {n: 1.0 / len(names) for n in names}
    return {n: w / total for n, w in chosen.items()}


def _model_markets(m: Markets) -> dict[str, object]:
    return {"p": [m.p_home, m.p_draw, m.p_away], "total": list(m.total_pmf)}


def build_forecast(
    fixture: Fixture,
    forms: Mapping[int, TeamForm],
    models: Mapping[str, GridModel],
    weights: Mapping[str, float],
    baseline: FrequencyBaseline,
    created_at: str,
    *,
    threshold: float = DRIFT_THRESHOLD_GOALS,
    min_matches: int = MIN_TEAM_MATCHES,
) -> ForecastRow:
    key = fixture_key(fixture.match_date, fixture.comp_code, fixture.home_id, fixture.away_id)
    assessment = assess_fixture(
        fixture.home_id, fixture.away_id, forms, threshold=threshold, min_matches=min_matches
    )
    detail: dict[str, object] = {"drift": assessment.as_dict()}

    def row(verdict: str, ensemble: Markets | None = None, **extra: str | None) -> ForecastRow:
        return ForecastRow(
            fixture_key=key,
            comp_code=fixture.comp_code,
            match_date=fixture.match_date.isoformat(),
            kickoff_utc=fixture.kickoff_utc,
            home_team_id=fixture.home_id,
            away_team_id=fixture.away_id,
            verdict=verdict,
            ensemble=ensemble,
            total_json=extra.get("total_json"),
            models_json=extra.get("models_json"),
            weights_json=extra.get("weights_json"),
            baseline_json=extra.get("baseline_json"),
            detail_json=_dump(detail),
            created_at=created_at,
        )

    if assessment.verdict != OK:
        return row(assessment.verdict)

    grids: dict[str, Grid] = {}
    left_out: dict[str, str] = {}
    for name in sorted(models):
        model = models[name]
        if not (model.knows(fixture.home_id) and model.knows(fixture.away_id)):
            left_out[name] = "unknown_team"
            continue
        try:
            grids[name] = model.grid(fixture.home_id, fixture.away_id, fixture.comp_code)
        except (GridError, ArithmeticError, ValueError) as exc:
            left_out[name] = f"grid_failed: {type(exc).__name__}"
    if left_out:
        detail["models_left_out"] = left_out
    if not grids:
        return row(NO_MODEL)

    names = sorted(grids)
    applied = renormalise(weights, names)
    pooled = mix_grids([grids[n] for n in names], [applied[n] for n in names])
    ensemble = markets(pooled)
    return row(
        OK,
        ensemble,
        total_json=_dump(list(ensemble.total_pmf)),
        models_json=_dump({n: _model_markets(markets(grids[n])) for n in names}),
        weights_json=_dump(applied),
        baseline_json=_dump(baseline.forecast(fixture.comp_code).as_dict()),
    )


def build_forecasts(
    fixtures: Iterable[Fixture],
    forms: Mapping[int, TeamForm],
    models: Mapping[str, GridModel],
    weights: Mapping[str, float],
    baseline: FrequencyBaseline,
    created_at: str,
    *,
    threshold: float = DRIFT_THRESHOLD_GOALS,
    min_matches: int = MIN_TEAM_MATCHES,
) -> list[ForecastRow]:
    """One row per fixture, de-duplicated by ``fixture_key`` (a duplicate fixture row keeps the
    first), in input order."""
    seen: set[str] = set()
    out: list[ForecastRow] = []
    for fixture in fixtures:
        key = fixture_key(fixture.match_date, fixture.comp_code, fixture.home_id, fixture.away_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            build_forecast(
                fixture,
                forms,
                models,
                weights,
                baseline,
                created_at,
                threshold=threshold,
                min_matches=min_matches,
            )
        )
    return out
