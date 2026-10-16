"""Types shared by the models, the backtest and the fit job."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from footy.models.grid import Grid
from footy.scoring.baseline import Result

UCL_ONLY_LEAGUE = "UCL_ONLY"  # league group of clubs with no domestic league among the ten

MODEL_DC = "dc"
MODEL_PI = "pi"
MODEL_BP = "bp"
MODELS: tuple[str, ...] = (MODEL_DC, MODEL_PI, MODEL_BP)


@dataclass(frozen=True)
class TrainingMatch(Result):
    """A verified finished match (90-minute score) inside the training window."""

    match_date: date
    home_id: int
    away_id: int
    season: str = ""


@dataclass(frozen=True)
class FitConfig:
    """Starting values from architecture sections 8.2 and 8.3. All are **unvalidated**: they are
    tuned on history in the backtest and snapshotted into ``model_runs.config_json``."""

    window_days: int = 1095  # ADR-009
    half_life_days: float = 300.0  # time decay: weight = 0.5 ** (age / half_life)
    shrink_team: float = 4.0  # ridge pulling team attack/defence toward their league mean
    shrink_league: float = 0.1  # weak ridge on league offsets (makes the level identifiable)
    param_bound: float = 3.0  # box bound on every raw parameter
    rho_bound: float = 0.3  # Dixon-Coles low-score correction
    max_abs_strength: float = 2.0  # sanity: |attack| and |defence| of every team
    min_mean_lambda: float = 0.3  # sanity: mean fitted rate per competition
    max_mean_lambda: float = 3.5
    max_iterations: int = 3000  # the real data needed more than 500 in a few folds (bp)
    tolerance: float = 1e-10  # relative objective change that stops the optimiser
    min_matches: int = 50  # refuse to fit on fewer weighted rows than this

    def as_dict(self) -> dict[str, object]:
        return {
            "window_days": self.window_days,
            "half_life_days": self.half_life_days,
            "shrink_team": self.shrink_team,
            "shrink_league": self.shrink_league,
            "param_bound": self.param_bound,
            "rho_bound": self.rho_bound,
            "max_abs_strength": self.max_abs_strength,
            "min_mean_lambda": self.min_mean_lambda,
            "max_mean_lambda": self.max_mean_lambda,
            "max_iterations": self.max_iterations,
            "tolerance": self.tolerance,
            "min_matches": self.min_matches,
        }


class ModelFitError(Exception):
    """Convergence failed or a sanity check did not hold; the model is stored as ``failed``."""


class GridModel(Protocol):
    """What the backtest and the publisher need from a fitted model."""

    name: str

    def knows(self, team_id: int) -> bool: ...

    def grid(self, home_id: int, away_id: int, comp_code: str) -> Grid: ...

    def to_payload(self) -> dict[str, object]: ...


@dataclass(frozen=True)
class FitOutcome:
    """Result of one model fit, ``ok`` or ``failed`` (section 8.2 failure semantics)."""

    model: str
    status: str  # "ok" or "failed"
    payload: dict[str, object] | None
    error: str | None
    diagnostics: dict[str, object] = field(default_factory=dict)
    fitted: GridModel | None = None


Fitter = Callable[[], tuple[GridModel, dict[str, object]]]


def run_fit(name: str, fitter: Fitter) -> FitOutcome:
    """Run a fit; a ``ModelFitError`` (or a numerical failure) becomes a ``failed`` outcome."""
    try:
        fitted, diagnostics = fitter()
    except ModelFitError as exc:
        return FitOutcome(name, "failed", None, str(exc))
    except (ArithmeticError, ValueError, FloatingPointError) as exc:
        return FitOutcome(name, "failed", None, f"numerical failure: {type(exc).__name__}: {exc}")
    return FitOutcome(name, "ok", fitted.to_payload(), None, diagnostics, fitted)


LeagueMap = Mapping[int, str]
