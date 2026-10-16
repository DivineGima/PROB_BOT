"""The fitters the backtest and the fit job can run, by model name (architecture section 8.2).

Adding a model is additive: register its fitter in ``FITTERS`` and its payload loader in
``load_model``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date

from footy.models.bivariate_poisson import BpModel, fit_bp_outcome
from footy.models.dixon_coles import DcModel, fit_dc_outcome
from footy.models.pi_rating import PiModel, fit_pi_outcome
from footy.models.types import (
    MODEL_BP,
    MODEL_DC,
    MODEL_PI,
    MODELS,
    FitConfig,
    FitOutcome,
    GridModel,
    LeagueMap,
    TrainingMatch,
)

Fitter = Callable[[Sequence[TrainingMatch], LeagueMap, date, FitConfig], FitOutcome]

FITTERS: dict[str, Fitter] = {
    MODEL_DC: lambda matches, leagues, as_of, config: fit_dc_outcome(
        matches, leagues, as_of, config
    ),
    MODEL_PI: lambda matches, leagues, as_of, config: fit_pi_outcome(
        matches, leagues, as_of, config
    ),
    MODEL_BP: lambda matches, leagues, as_of, config: fit_bp_outcome(
        matches, leagues, as_of, config
    ),
}
assert set(FITTERS) == set(MODELS)  # noqa: S101 (a model added to MODELS must be registered)


def fitters_for(names: Sequence[str]) -> Mapping[str, Fitter]:
    unknown = [n for n in names if n not in FITTERS]
    if unknown:
        raise ValueError(f"unknown model(s): {', '.join(unknown)}")
    return {n: FITTERS[n] for n in names}


def load_model(name: str, payload: dict[str, object]) -> GridModel:
    """Rebuild a fitted model from its stored payload."""
    if name == MODEL_DC:
        return DcModel.from_payload(payload)
    if name == MODEL_PI:
        return PiModel.from_payload(payload)
    if name == MODEL_BP:
        return BpModel.from_payload(payload)
    raise ValueError(f"unknown model {name!r}")


def fit_model(
    name: str,
    matches: Sequence[TrainingMatch],
    leagues: LeagueMap,
    as_of: date,
    config: FitConfig,
) -> FitOutcome:
    return fitters_for([name])[name](matches, leagues, as_of, config)


def team_values(name: str, payload: dict[str, object]) -> dict[int, tuple[float, float]]:
    """Per-team strength values used by the promotion gate's stability guard (section 8.6):
    attack and defence for ``dc`` and ``bp``, home and away rating for ``pi``."""
    teams = payload.get("teams")
    if name not in FITTERS or not isinstance(teams, dict):
        raise ValueError(f"cannot read team values of model {name!r}")
    return {int(t): (float(v[0]), float(v[1])) for t, v in teams.items()}
