"""``footy fit``: fit the three models, weight the ensemble, snapshot team form, write the run.

Section 7.9 steps "fit dc / pi / bp, weights, baselines, team_form" and 8.2 failure semantics:
a model that fails convergence or sanity checks is stored ``failed`` with its reason and is never
replaced by yesterday's parameters; a run where every model failed is stored ``failed`` and the
previous run stays active. The run is written as ``building``; ``footy publish`` decides whether it
becomes active.

Orchestration only: SQL is in ``footy.repo``, maths in ``footy.models``, ``footy.ensemble`` and
``footy.form``.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime

from footy.alerts import raise_alert
from footy.config import (
    DRIFT_THRESHOLD_GOALS,
    ENSEMBLE_KAPPA,
    ENSEMBLE_RECENT,
    ENSEMBLE_SHRINK_N,
    GATE_FORM_COVERAGE,
    GATE_PAYLOAD_COVERAGE,
    MIN_TEAM_MATCHES,
    STABILITY_BOUND,
    STALE_HOURS,
)
from footy.ensemble.weights import ensemble_weights, prior_from_backtest
from footy.errors import DataError, ExitCode, FootyError
from footy.form.snapshot import build_team_form
from footy.ingest.pipeline import JobResult
from footy.models.pi_rating import PiParams
from footy.models.registry import fit_model, fitters_for
from footy.models.structure import window_matches
from footy.models.types import MODELS, FitConfig, FitOutcome
from footy.repo.d1_client import D1Error, MemoryProgress
from footy.repo.matches import MatchesRepo
from footy.repo.models import STATUS_BUILDING, STATUS_FAILED, ModelRegistryRepo, ParamRow, RunRecord
from footy.repo.ops import OpsRepo
from footy.repo.ports import Database
from footy.repo.training import TrainingRepo
from footy.scoring import FrequencyBaseline

log = logging.getLogger("footy.fit")

CODE_VERSION = "stage-4"


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_id_for(at: str) -> str:
    """``R`` + UTC timestamp, e.g. ``R20261016T011742Z`` (section 5.4)."""
    return "R" + at.replace("-", "").replace(":", "")


def payload_text(payload: dict[str, object]) -> str:
    """The exact text stored in ``model_params.payload_json`` (the hash is taken over it)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def payload_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _param_row(outcome: FitOutcome) -> ParamRow:
    if outcome.status != "ok" or outcome.payload is None:
        return ParamRow(outcome.model, "failed", None, None, None, outcome.error or "failed")
    text = payload_text(outcome.payload)
    version = outcome.payload.get("payload_version")
    return ParamRow(
        outcome.model,
        "ok",
        int(version) if isinstance(version, int) else 1,
        text,
        payload_sha256(text),
        None,
    )


def run_config(
    config: FitConfig, models: Sequence[str], baseline: FrequencyBaseline
) -> dict[str, object]:
    """Snapshot of every threshold the Worker and the gate rely on (section 5.4); unvalidated."""
    return {
        "unvalidated": True,
        "models": list(models),
        "fit": config.as_dict(),
        "pi": PiParams().as_dict(),
        "min_team_matches": MIN_TEAM_MATCHES,
        "drift": {"basis": "goals only", "threshold_goals": DRIFT_THRESHOLD_GOALS},
        "stale_hours": STALE_HOURS,
        "gate": {
            "stability_bound": STABILITY_BOUND,
            "form_coverage": GATE_FORM_COVERAGE,
            "payload_coverage": GATE_PAYLOAD_COVERAGE,
        },
        "ensemble": {
            "kappa": ENSEMBLE_KAPPA,
            "recent": ENSEMBLE_RECENT,
            "shrink_n": ENSEMBLE_SHRINK_N,
        },
        "baseline": baseline.snapshot(),
    }


def run_fit_job(
    db: Database,
    *,
    models: Sequence[str] = MODELS,
    as_of: date | None = None,
    config: FitConfig | None = None,
    now: Callable[[], str] = _utc_now,
    git_sha: str | None = None,
) -> JobResult:
    cfg = config or FitConfig()
    ops = OpsRepo(db)
    started = now()
    summary: dict[str, object] = {"mode": "fit"}
    try:
        job_id = ops.start_job("fit", started, git_sha)
    except D1Error as exc:
        return JobResult(ExitCode.UNEXPECTED, {**summary, "error": str(exc)})
    try:
        try:
            fitters_for(models)  # fail early on an unknown model name
        except ValueError as exc:
            raise DataError(str(exc)) from None
        training = TrainingRepo(db)
        every = training.finished_matches()
        if not every:
            raise DataError("no verified results in the database: run `footy bootstrap` first")
        cutoff = max(m.match_date for m in every)
        day = as_of if as_of is not None else cutoff
        matches = [m for m in every if m.match_date <= day]
        window = window_matches(matches, day, cfg.window_days)
        if len(window) < cfg.min_matches:
            raise DataError(f"only {len(window)} results in the training window")
        leagues = training.league_groups()
        active_ids = training.active_team_ids()

        baseline = FrequencyBaseline.from_results(window)
        outcomes = [fit_model(name, matches, leagues, day, cfg) for name in models]
        ok = [o.model for o in outcomes if o.status == "ok"]
        failed = [o for o in outcomes if o.status != "ok"]

        run_id = run_id_for(started)
        registry = ModelRegistryRepo(db)
        if registry.get_run(run_id) is not None:
            raise DataError(f"run {run_id} already exists: wait a second and run again")

        prior = prior_from_backtest(ops.latest_job_summary("backtest"), ok) if ok else {}
        weights = ensemble_weights(ok, prior_rps=prior) if ok else None
        forms = build_team_form(matches, active_ids, day, cfg.window_days) if ok else []
        diagnostics: dict[str, object] = {
            "models": {
                o.model: {"status": o.status, "error": o.error, "diagnostics": o.diagnostics}
                for o in outcomes
            },
            "n_matches_window": len(window),
            "n_teams_training": len({m.home_id for m in window} | {m.away_id for m in window}),
            "freshness": MatchesRepo(db).freshness(),
            "failed_models": [o.model for o in failed],
        }
        record = RunRecord(
            run_id=run_id,
            status=STATUS_BUILDING if ok else STATUS_FAILED,
            started_at=started,
            finished_at=None if ok else now(),
            data_cutoff_utc=cutoff.isoformat(),
            training_from=min(m.match_date for m in window).isoformat(),
            training_to=max(m.match_date for m in window).isoformat(),
            git_sha=git_sha,
            code_version=CODE_VERSION,
            config_json=json.dumps(run_config(cfg, models, baseline), sort_keys=True),
            ensemble_json=json.dumps(weights.as_dict() if weights else {}, sort_keys=True),
            diagnostics_json=json.dumps(diagnostics, sort_keys=True, default=str),
        )
        registry.write_run(record, [_param_row(o) for o in outcomes], forms, MemoryProgress())

        for o in failed:
            raise_alert(
                ops,
                now(),
                f"fit:{o.model}:{day.isoformat()}",
                "model_failed",
                {"model": o.model, "error": o.error, "run_id": run_id},
            )
        if not ok:
            raise_alert(
                ops, now(), f"fit:all:{day.isoformat()}", "all_models_failed", {"run_id": run_id}
            )
        summary.update(
            {
                "run_id": run_id,
                "run_status": record.status,
                "data_cutoff": cutoff.isoformat(),
                "as_of": day.isoformat(),
                "models_ok": ok,
                "models_failed": {o.model: o.error for o in failed},
                "ensemble": weights.as_dict() if weights else None,
                "team_form_rows": len(forms),
                "matches_in_window": len(window),
            }
        )
    except (FootyError, D1Error) as exc:
        try:
            ops.finish_job(job_id, now(), "failed", summary, error=str(exc))
        except D1Error:
            log.warning("could not record the failed job in the database")
        code = exc.exit_code if isinstance(exc, FootyError) else ExitCode.UNEXPECTED
        return JobResult(code, {**summary, "error": str(exc)})

    code = ExitCode.OK if not failed else ExitCode.FIT
    ops.finish_job(job_id, now(), "ok" if code == ExitCode.OK else "partial", summary)
    return JobResult(code, summary)
