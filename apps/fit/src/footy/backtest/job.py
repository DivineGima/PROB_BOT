"""``footy backtest``: read verified results, walk forward, report, record the job.

Orchestration only: SQL is in ``footy.repo``, maths in ``footy.models`` and ``footy.scoring``, the
job bookkeeping in ``footy.jobs``. The summary is safe to print and is stored in
``job_runs.summary_json`` (no per-match data).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import date, timedelta

from footy.alerts import raise_alert
from footy.backtest.regression import compare_with_previous
from footy.backtest.report import format_report
from footy.backtest.walkforward import BacktestConfig, BacktestResult, run_backtest
from footy.clock import utc_now
from footy.config import BACKTEST_REGRESSION_TOLERANCE
from footy.errors import DataError, ExitCode
from footy.jobs import JobResult, run_job
from footy.models.registry import Fitter, fitters_for
from footy.models.types import MODEL_DC, MODEL_PI, FitConfig
from footy.repo.ops import OpsRepo
from footy.repo.ports import Database
from footy.repo.training import TrainingRepo

log = logging.getLogger("footy.backtest")

DEFAULT_TEST_DAYS = 365
DEFAULT_FOLD_DAYS = 14
MAX_SWEEP_CONFIGS = 12


def _rps(result: BacktestResult, model: str) -> float | None:
    overall = result.models[model].overall()
    return overall.rps_1x2 if overall is not None else None


def _memoised(fitter: Fitter) -> Fitter:
    """Cache a fitter across the sweep. The pi-rating does not depend on the team shrinkage, so
    refitting it for every shrinkage value repeats identical work; the key holds every setting it
    does read."""
    cache: dict[tuple[object, ...], object] = {}

    def wrapper(matches, leagues, as_of, config):  # type: ignore[no-untyped-def]
        key = (
            as_of,
            len(matches),
            config.window_days,
            config.half_life_days,
            config.min_matches,
            config.min_mean_lambda,
            config.max_mean_lambda,
        )
        if key not in cache:
            cache[key] = fitter(matches, leagues, as_of, config)
        return cache[key]

    return wrapper


def run_backtest_job(
    db: Database,
    *,
    models: Sequence[str] = (MODEL_DC,),
    test_days: int = DEFAULT_TEST_DAYS,
    fold_days: int = DEFAULT_FOLD_DAYS,
    half_lives: Sequence[float] | None = None,
    shrinks: Sequence[float] | None = None,
    now: Callable[[], str] = utc_now,
    git_sha: str | None = None,
    report_sink: Callable[[str], None] | None = None,
    fail_on_regression: bool = False,
    regression_tolerance: float = BACKTEST_REGRESSION_TOLERANCE,
) -> JobResult:
    """Walk-forward backtest over the last ``test_days`` days of stored results. With several
    ``half_lives`` or ``shrinks`` every combination appears in the sweep table (starting values are
    chosen from it by hand, never auto-applied). The reported result, which the fit job may read
    as its ensemble prior, is the combination equal to the production defaults when the sweep
    contains it, otherwise the first one; the summary names the settings and models it used.

    The result is also compared with the previous comparable backtest (ADR-046). A model that got
    worse by more than ``regression_tolerance`` is recorded in the summary and raises an alert
    event; with ``fail_on_regression`` the job then ends with the fit-failure exit code."""
    ops = OpsRepo(db)
    summary: dict[str, object] = {"mode": "backtest"}

    def body() -> ExitCode:
        if test_days < 1 or fold_days < 1:
            raise DataError("test_days and fold_days must be at least 1")
        defaults = FitConfig()
        half_life_values = list(half_lives) if half_lives else [defaults.half_life_days]
        shrink_values = list(shrinks) if shrinks else [defaults.shrink_team]
        if len(half_life_values) * len(shrink_values) > MAX_SWEEP_CONFIGS:
            raise DataError(f"at most {MAX_SWEEP_CONFIGS} sweep combinations")
        try:
            fitters = dict(fitters_for(models))
        except ValueError as exc:
            raise DataError(str(exc)) from None
        if MODEL_PI in fitters:
            fitters[MODEL_PI] = _memoised(fitters[MODEL_PI])

        # Read before this job's own row can matter: it is still 'running', so it is never picked.
        previous = ops.latest_job_summary("backtest")
        repo = TrainingRepo(db)
        matches = repo.finished_matches()
        if not matches:
            raise DataError("no verified results in the database: run `footy bootstrap` first")
        cutoff: date = max(m.match_date for m in matches)
        config = BacktestConfig(
            test_from=cutoff - timedelta(days=test_days - 1), test_to=cutoff, fold_days=fold_days
        )
        before = sum(1 for m in matches if m.match_date < config.test_from)
        if before < defaults.min_matches:
            raise DataError(f"only {before} results before {config.test_from}: shorten --test-days")
        leagues = repo.league_groups()
        summary.update(
            {
                "data_cutoff": cutoff.isoformat(),
                "results": len(matches),
                "models": list(models),
                "test_days": test_days,
            }
        )

        sweep_rows: list[dict[str, object]] = []
        reported: BacktestResult | None = None
        for half_life in half_life_values:
            for shrink in shrink_values:
                fit_config = replace(defaults, half_life_days=half_life, shrink_team=shrink)
                result = run_backtest(matches, leagues, fitters, config, fit_config)
                is_default = half_life == defaults.half_life_days and shrink == defaults.shrink_team
                if reported is None or (is_default and not _is_default(reported, defaults)):
                    reported = result
                row: dict[str, object] = {"half_life_days": half_life, "shrink_team": shrink}
                for name in models:
                    row[f"rps_{name}"] = _rps(result, name)
                sweep_rows.append(row)
                log.info("backtest half_life=%s shrink_team=%s done", half_life, shrink)
        assert reported is not None  # noqa: S101 (at least one combination ran)
        summary["result"] = reported.summary()
        if len(sweep_rows) > 1:
            summary["sweep"] = sweep_rows
        if report_sink is not None:
            report_sink(
                format_report(reported.summary(), sweep_rows if len(sweep_rows) > 1 else ())
            )

        if reported.forecast_matches == 0:
            raise DataError("the backtest produced no forecasts (models failed or too little data)")
        failed_folds = sum(len(reported.fold_failures.get(m, [])) for m in models)

        regression = compare_with_previous(
            previous,
            {"models": list(models), "test_days": test_days, "result": summary["result"]},
            tolerance=regression_tolerance,
        )
        summary["regression"] = regression
        regressed = regression["regressed"]
        if regressed:
            raise_alert(
                ops,
                now(),
                f"backtest_regression:{cutoff.isoformat()}",
                "backtest_regression",
                {"regressed": regressed, "changes": regression.get("changes")},
            )
        if failed_folds or (regressed and fail_on_regression):
            return ExitCode.FIT
        return ExitCode.OK

    return run_job(ops, "backtest", now=now, git_sha=git_sha, summary=summary, body=body)


def _is_default(result: BacktestResult, defaults: FitConfig) -> bool:
    return (
        result.fit_config.half_life_days == defaults.half_life_days
        and result.fit_config.shrink_team == defaults.shrink_team
    )
