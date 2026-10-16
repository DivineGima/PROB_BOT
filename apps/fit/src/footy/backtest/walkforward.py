"""Walk-forward backtest (architecture sections 8.7 and 9.5, essentials Stage 3 step 6).

The test period is cut into folds. For each fold the models are fitted on matches strictly BEFORE
the fold (no leakage), the fold's matches are forecast, and every forecast is scored with the same
rules as the live prediction log. The league-frequency baseline for each fold is built from the same
training matches, so the comparison is fair: a model must beat "what a league usually does".

Results are labelled as tuning on history, not validation: the same matches may be used to choose
the half-life and shrinkage (``sweep``), so the numbers are optimistic by construction.

Matches are only forecast when both teams have at least ``MIN_TEAM_MATCHES`` training matches
(the live ``INSUFFICIENT_HISTORY`` rule, FR-10); the number skipped is reported.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

from footy.models.grid import markets
from footy.models.structure import window_matches
from footy.models.types import FitConfig, FitOutcome, LeagueMap, TrainingMatch
from footy.scoring import (
    FrequencyBaseline,
    MeanScores,
    ScoredForecast,
    mean_scores,
    score_forecast,
)

MIN_TEAM_MATCHES = 10

Fitter = Callable[[Sequence[TrainingMatch], LeagueMap, date, FitConfig], FitOutcome]


@dataclass(frozen=True)
class BacktestConfig:
    test_from: date
    test_to: date
    fold_days: int = 14
    min_team_matches: int = MIN_TEAM_MATCHES


@dataclass
class _Scores:
    """Scored forecasts of one forecaster, keyed by competition."""

    by_comp: dict[str, list[ScoredForecast]] = field(default_factory=dict)
    # (model RPS, baseline RPS) for the same match, per competition
    paired: dict[str, list[tuple[float, float]]] = field(default_factory=dict)

    def add(self, comp: str, scored: ScoredForecast, baseline_rps: float | None = None) -> None:
        self.by_comp.setdefault(comp, []).append(scored)
        if baseline_rps is not None:
            self.paired.setdefault(comp, []).append((scored.rps_1x2, baseline_rps))

    def overall(self) -> MeanScores | None:
        flat = [s for scores in self.by_comp.values() for s in scores]
        return mean_scores(flat) if flat else None

    def comp_means(self) -> dict[str, MeanScores]:
        return {c: mean_scores(s) for c, s in sorted(self.by_comp.items()) if s}


@dataclass
class BacktestResult:
    config: BacktestConfig
    fit_config: FitConfig
    folds: int = 0
    fold_failures: dict[str, list[str]] = field(default_factory=dict)  # model -> errors
    forecast_matches: int = 0
    skipped_insufficient_history: int = 0
    skipped_unknown_team: Counter[str] = field(default_factory=Counter)
    models: dict[str, _Scores] = field(default_factory=dict)
    baseline: _Scores = field(default_factory=_Scores)

    def summary(self) -> dict[str, object]:
        """A JSON-safe summary: overall and per-competition means for each model and the baseline,
        the skill against the baseline and the paired difference with its standard error."""
        base_overall = self.baseline.overall()
        out: dict[str, object] = {
            "label": "tuning on history, not validation",
            "test_from": self.config.test_from.isoformat(),
            "test_to": self.config.test_to.isoformat(),
            "fold_days": self.config.fold_days,
            "folds": self.folds,
            "forecast_matches": self.forecast_matches,
            "skipped_insufficient_history": self.skipped_insufficient_history,
            "fit_config": self.fit_config.as_dict(),
            "fold_failures": {m: len(e) for m, e in sorted(self.fold_failures.items())},
            "baseline": _means_dict(base_overall, self.baseline.comp_means()),
            "models": {},
        }
        models: dict[str, object] = {}
        for name, scores in sorted(self.models.items()):
            overall = scores.overall()
            entry = _means_dict(overall, scores.comp_means())
            pairs = [p for ps in scores.paired.values() for p in ps]
            if overall is not None and pairs:
                diffs = [m - b for m, b in pairs]
                mean_diff = sum(diffs) / len(diffs)
                baseline_mean = sum(b for _m, b in pairs) / len(pairs)
                entry["rps_skill_vs_baseline"] = -mean_diff / baseline_mean
                entry["paired_rps_diff_mean"] = mean_diff  # negative: the model is better
                entry["paired_rps_diff_se"] = _standard_error(diffs)
                entry["beats_baseline"] = mean_diff < 0
                entry["per_competition_beats_baseline"] = {
                    c: sum(m - b for m, b in ps) < 0 for c, ps in sorted(scores.paired.items())
                }
            models[name] = entry
        out["models"] = models
        return out


def _means_dict(
    overall: MeanScores | None, per_comp: Mapping[str, MeanScores]
) -> dict[str, object]:
    return {
        "overall": overall.as_dict() if overall is not None else None,
        "per_competition": {c: m.as_dict() for c, m in per_comp.items()},
    }


def _standard_error(values: Sequence[float]) -> float:
    n = len(values)
    if n < 2:
        return float("nan")
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(variance / n)


def folds_for(config: BacktestConfig) -> list[tuple[date, date]]:
    """Consecutive ``fold_days``-day folds covering ``test_from .. test_to`` inclusive."""
    if config.fold_days < 1:
        raise ValueError("fold_days must be at least 1")
    if config.test_to < config.test_from:
        raise ValueError("test_to is before test_from")
    folds: list[tuple[date, date]] = []
    start = config.test_from
    while start <= config.test_to:
        end = min(start + timedelta(days=config.fold_days - 1), config.test_to)
        folds.append((start, end))
        start = end + timedelta(days=1)
    return folds


def _team_counts(matches: Sequence[TrainingMatch]) -> Counter[int]:
    counts: Counter[int] = Counter()
    for m in matches:
        counts[m.home_id] += 1
        counts[m.away_id] += 1
    return counts


def run_backtest(
    matches: Sequence[TrainingMatch],
    leagues: LeagueMap,
    fitters: Mapping[str, Fitter],
    config: BacktestConfig,
    fit_config: FitConfig | None = None,
) -> BacktestResult:
    """Walk forward over ``config.test_from .. config.test_to``. ``matches`` must hold every
    verified result (training and test); nothing at or after a fold's first day is used to fit
    that fold."""
    cfg = fit_config or FitConfig()
    result = BacktestResult(config=config, fit_config=cfg)
    for name in fitters:
        result.models[name] = _Scores()
    ordered = sorted(matches, key=lambda m: m.match_date)

    for fold_start, fold_end in folds_for(config):
        as_of = fold_start - timedelta(days=1)
        train = [m for m in ordered if m.match_date <= as_of]
        test = [m for m in ordered if fold_start <= m.match_date <= fold_end]
        if not test:
            continue
        result.folds += 1
        in_window = window_matches(train, as_of, cfg.window_days)
        if not in_window:
            continue
        counts = _team_counts(in_window)
        baseline = FrequencyBaseline.from_results(in_window)

        fitted = {}
        for name, fitter in fitters.items():
            outcome = fitter(train, leagues, as_of, cfg)
            if outcome.status == "ok" and outcome.fitted is not None:
                fitted[name] = outcome.fitted
            else:
                result.fold_failures.setdefault(name, []).append(outcome.error or "failed")

        for m in test:
            if (
                counts[m.home_id] < config.min_team_matches
                or counts[m.away_id] < config.min_team_matches
            ):
                result.skipped_insufficient_history += 1
                continue
            base_scored = score_forecast(baseline.forecast(m.comp_code), m.goals_home, m.goals_away)
            forecasts: dict[str, ScoredForecast] = {}
            for name, model in fitted.items():
                if not (model.knows(m.home_id) and model.knows(m.away_id)):
                    result.skipped_unknown_team[name] += 1
                    continue
                forecasts[name] = score_forecast(
                    markets(model.grid(m.home_id, m.away_id, m.comp_code)),
                    m.goals_home,
                    m.goals_away,
                )
            if not forecasts:
                continue
            # The baseline is scored on exactly the matches at least one model forecast, so the
            # comparison uses the same sample.
            result.forecast_matches += 1
            result.baseline.add(m.comp_code, base_scored)
            for name, scored in forecasts.items():
                result.models[name].add(m.comp_code, scored, base_scored.rps_1x2)
    return result
