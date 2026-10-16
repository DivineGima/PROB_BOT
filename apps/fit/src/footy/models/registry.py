"""The fitters the backtest and the fit job can run, by model name (architecture section 8.2).

Adding a model is additive: register its fitter in ``FITTERS`` and its payload loader in
``load_model``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date

from footy.models.dixon_coles import DcModel, fit_dc_outcome
from footy.models.types import MODEL_DC, FitConfig, FitOutcome, GridModel, LeagueMap, TrainingMatch

Fitter = Callable[[Sequence[TrainingMatch], LeagueMap, date, FitConfig], FitOutcome]

FITTERS: dict[str, Fitter] = {
    MODEL_DC: lambda matches, leagues, as_of, config: fit_dc_outcome(
        matches, leagues, as_of, config
    ),
}


def fitters_for(names: Sequence[str]) -> Mapping[str, Fitter]:
    unknown = [n for n in names if n not in FITTERS]
    if unknown:
        raise ValueError(f"unknown model(s): {', '.join(unknown)}")
    return {n: FITTERS[n] for n in names}


def load_model(name: str, payload: dict[str, object]) -> GridModel:
    """Rebuild a fitted model from its stored payload."""
    if name == MODEL_DC:
        return DcModel.from_payload(payload)
    raise ValueError(f"unknown model {name!r}")


def fit_model(
    name: str,
    matches: Sequence[TrainingMatch],
    leagues: LeagueMap,
    as_of: date,
    config: FitConfig,
) -> FitOutcome:
    return fitters_for([name])[name](matches, leagues, as_of, config)
