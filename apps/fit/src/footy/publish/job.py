"""``footy publish``: run the promotion gate and, if it passes, make the run active (section 8.6).

* pass: ONE atomic batch makes the run ``active``, points ``active_run`` at it and supersedes the
  previous run; runs beyond the newest 30 are pruned (ADR-004);
* fail: the run is ``rejected`` with every reason recorded, the previous run stays active and an
  alert event is written (exit code 4);
* repeating a publish of the run that is already active is a no-op (section 9.6);
* ``rollback``: point ``active_run`` back at a retained ``superseded`` run, with no gate (it was
  active before). This is the documented rollback command (``footy publish --rollback RUN_ID``);
* ``accept_drift``: for ONE named run, skip only the stability guard after a human has decided a
  large move is real (a data correction, a league re-link). The structural checks still apply and
  the override is recorded as an ``info`` event; without it a legitimate large move would reject
  every later run, because each is compared with the same active run.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from footy.alerts import raise_alert
from footy.clock import utc_now
from footy.config import RUNS_KEPT
from footy.errors import DataError, ExitCode
from footy.jobs import JobResult, run_job
from footy.publish.gate import GateInput, decode_payload, evaluate_gate
from footy.repo.models import (
    STATUS_ACTIVE,
    STATUS_BUILDING,
    STATUS_SUPERSEDED,
    ModelRegistryRepo,
)
from footy.repo.ops import OpsRepo
from footy.repo.ports import Database


def _load(text: str) -> dict[str, object]:
    try:
        loaded = json.loads(text)
    except ValueError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _active_payloads(
    registry: ModelRegistryRepo,
) -> tuple[dict[str, dict[str, object]], dict[str, str]]:
    """Verified payloads of the active run by model, and the models whose active payload did NOT
    verify (with the reason), so the stability guard never compares against a corrupt payload."""
    active = registry.active_run_id()
    if active is None:
        return {}, {}
    verified: dict[str, dict[str, object]] = {}
    skipped: dict[str, str] = {}
    for row in registry.load_params(active):
        if row.status != "ok":
            continue
        payload, problem = decode_payload(row)
        if payload is None:
            skipped[row.model] = f"the active run's payload does not verify ({problem})"
        else:
            verified[row.model] = payload
    return verified, skipped


def run_publish_job(
    db: Database,
    *,
    run_id: str | None = None,
    rollback: str | None = None,
    accept_drift: bool = False,
    now: Callable[[], str] = utc_now,
    git_sha: str | None = None,
    keep: int = RUNS_KEPT,
) -> JobResult:
    ops = OpsRepo(db)
    registry = ModelRegistryRepo(db)
    summary: dict[str, object] = {"mode": "rollback" if rollback else "publish"}

    def body() -> ExitCode:
        if accept_drift and (run_id is None or rollback is not None):
            raise DataError("--accept-drift needs an explicit --run-id (and no --rollback)")
        if rollback is not None:
            _rollback(registry, rollback, now(), summary)
            return ExitCode.OK
        return _publish(registry, ops, run_id, accept_drift, now, summary, keep)

    return run_job(
        ops,
        "rollback" if rollback else "publish",
        now=now,
        git_sha=git_sha,
        summary=summary,
        body=body,
    )


def _rollback(
    registry: ModelRegistryRepo, target: str, at: str, summary: dict[str, object]
) -> None:
    run = registry.get_run(target)
    if run is None:
        raise DataError(f"run {target} does not exist (it may have been pruned)")
    if run.status == STATUS_ACTIVE and registry.active_run_id() == target:
        summary.update({"run_id": target, "result": "already active"})
        return
    if run.status != STATUS_SUPERSEDED:
        raise DataError(f"only a superseded run can be rolled back to; {target} is {run.status}")
    previous = registry.active_run_id()
    if not registry.promote(target, at):
        raise DataError(f"rollback to {target} did not take effect")
    summary.update({"run_id": target, "replaced": previous, "result": "rolled back"})


def _publish(
    registry: ModelRegistryRepo,
    ops: OpsRepo,
    run_id: str | None,
    accept_drift: bool,
    now: Callable[[], str],
    summary: dict[str, object],
    keep: int,
) -> ExitCode:
    run = registry.get_run(run_id) if run_id else registry.latest_run(STATUS_BUILDING)
    if run is None:
        raise DataError(
            f"run {run_id} does not exist"
            if run_id
            else "no 'building' run to publish: run `footy fit`"
        )
    summary["run_id"] = run.run_id
    if run.status == STATUS_ACTIVE and registry.active_run_id() == run.run_id:
        summary["result"] = "already active"
        return ExitCode.OK

    params = registry.load_params(run.run_id)
    form_rows, active_teams = registry.form_coverage(run.run_id)
    config = _load(run.config_json)
    diagnostics = _load(run.diagnostics_json)
    gate_config = config.get("gate")
    bound = gate_config.get("stability_bound") if isinstance(gate_config, dict) else None
    attempted = config.get("models")
    n_teams = diagnostics.get("n_teams_training")
    active_payloads, active_skipped = _active_payloads(registry)
    result = evaluate_gate(
        GateInput(
            run_status=run.status,
            attempted_models=[str(m) for m in attempted] if isinstance(attempted, list) else [],
            params=params,
            form_rows=form_rows,
            active_teams=active_teams,
            n_teams_training=int(n_teams) if isinstance(n_teams, int) else None,
            active_payloads=active_payloads,
            active_skipped=active_skipped,
            check_stability=not accept_drift,
            **({"stability_bound": float(bound)} if isinstance(bound, int | float) else {}),
        )
    )
    summary["gate"] = result.as_dict()

    if not result.passed:
        if run.status == STATUS_BUILDING:
            registry.reject(run.run_id, now(), {**diagnostics, "gate": result.as_dict()})
        raise_alert(
            ops,
            now(),
            f"publish:{run.run_id}",
            "run_rejected",
            {"run_id": run.run_id, "reasons": result.reasons},
        )
        summary["result"] = "rejected; the previous run stays active"
        summary["active_run_id"] = registry.active_run_id()
        return ExitCode.FIT

    previous = registry.active_run_id()
    if accept_drift:
        ops.record_event(
            now(),
            "info",
            "footy",
            "drift_accepted",
            {"run_id": run.run_id, "replaced": previous},
        )
        summary["drift_accepted"] = True
    if not registry.promote(run.run_id, now()):
        raise DataError(f"promotion of {run.run_id} did not take effect")
    pruned = registry.delete_runs(registry.prunable_run_ids(keep))
    summary.update(
        {
            "result": "promoted",
            "replaced": previous,
            "pruned_runs": pruned,
            "run_counts": registry.run_counts(),
        }
    )
    return ExitCode.OK
