"""``footy backtest``: read verified results, walk forward, report, record the job.

Orchestration only: SQL is in ``footy.repo``, maths in ``footy.models`` and ``footy.scoring``. The
summary is safe to print and is stored in ``job_runs.summary_json`` (no per-match data).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

from footy.backtest.report import format_report
from footy.backtest.walkforward import BacktestConfig, BacktestResult, run_backtest
from footy.errors import DataError, ExitCode, FootyError
from footy.ingest.pipeline import JobResult
from footy.models.registry import fitters_for
from footy.models.types import MODEL_DC, FitConfig
from footy.repo.d1_client import D1Error
from footy.repo.ops import OpsRepo
from footy.repo.ports import Database
from footy.repo.training import TrainingRepo

log = logging.getLogger("footy.backtest")

DEFAULT_TEST_DAYS = 365
DEFAULT_FOLD_DAYS = 14
MAX_SWEEP_CONFIGS = 12


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rps(result: BacktestResult, model: str) -> float | None:
    overall = result.models[model].overall()
    return overall.rps_1x2 if overall is not None else None


def run_backtest_job(
    db: Database,
    *,
    models: Sequence[str] = (MODEL_DC,),
    test_days: int = DEFAULT_TEST_DAYS,
    fold_days: int = DEFAULT_FOLD_DAYS,
    half_lives: Sequence[float] | None = None,
    shrinks: Sequence[float] | None = None,
    now: Callable[[], str] = _utc_now,
    git_sha: str | None = None,
    report_sink: Callable[[str], None] | None = None,
) -> JobResult:
    """Walk-forward backtest over the last ``test_days`` days of stored results. With several
    ``half_lives`` or ``shrinks`` the first combination is the reported run and every combination
    appears in the sweep table (starting values are chosen from it by hand, never auto-applied)."""
    ops = OpsRepo(db)
    job_id = ops.start_job("backtest", now(), git_sha)
    summary: dict[str, object] = {"mode": "backtest"}
    try:
        if test_days < 1 or fold_days < 1:
            raise DataError("test_days and fold_days must be at least 1")
        half_life_values = list(half_lives) if half_lives else [FitConfig().half_life_days]
        shrink_values = list(shrinks) if shrinks else [FitConfig().shrink_team]
        if len(half_life_values) * len(shrink_values) > MAX_SWEEP_CONFIGS:
            raise DataError(f"at most {MAX_SWEEP_CONFIGS} sweep combinations")
        fitters = fitters_for(models)

        repo = TrainingRepo(db)
        matches = repo.finished_matches()
        if not matches:
            raise DataError("no verified results in the database: run `footy bootstrap` first")
        cutoff: date = max(m.match_date for m in matches)
        config = BacktestConfig(
            test_from=cutoff - timedelta(days=test_days - 1), test_to=cutoff, fold_days=fold_days
        )
        before = sum(1 for m in matches if m.match_date < config.test_from)
        if before < FitConfig().min_matches:
            raise DataError(f"only {before} results before {config.test_from}: shorten --test-days")
        leagues = repo.league_groups()
        summary.update({"data_cutoff": cutoff.isoformat(), "results": len(matches)})

        base_fit = FitConfig()
        sweep_rows: list[dict[str, object]] = []
        first: BacktestResult | None = None
        for half_life in half_life_values:
            for shrink in shrink_values:
                fit_config = replace(base_fit, half_life_days=half_life, shrink_team=shrink)
                result = run_backtest(matches, leagues, fitters, config, fit_config)
                if first is None:
                    first = result
                row: dict[str, object] = {"half_life_days": half_life, "shrink_team": shrink}
                for name in models:
                    row[f"rps_{name}"] = _rps(result, name)
                sweep_rows.append(row)
                log.info("backtest half_life=%s shrink_team=%s done", half_life, shrink)
        assert first is not None  # noqa: S101 (at least one combination ran)
        summary["result"] = first.summary()
        if len(sweep_rows) > 1:
            summary["sweep"] = sweep_rows
        if report_sink is not None:
            report_sink(format_report(first.summary(), sweep_rows if len(sweep_rows) > 1 else ()))

        if first.forecast_matches == 0:
            raise DataError("the backtest produced no forecasts (models failed or too little data)")
    except (FootyError, D1Error) as exc:
        try:
            ops.finish_job(job_id, now(), "failed", summary, error=str(exc))
        except D1Error:
            log.warning("could not record the failed job in the database")
        code = exc.exit_code if isinstance(exc, FootyError) else ExitCode.UNEXPECTED
        return JobResult(code, {**summary, "error": str(exc)})

    failed_folds = sum(len(first.fold_failures.get(m, [])) for m in models)
    code = ExitCode.FIT if failed_folds else ExitCode.OK
    ops.finish_job(job_id, now(), "ok" if code == ExitCode.OK else "partial", summary)
    return JobResult(code, summary)
