"""What every ``footy`` job shares: its result type and the ``job_runs`` bookkeeping.

``run_job`` records the job, runs its body and records the outcome, so the jobs only contain their
own logic. Failure policy (section 9.4): an expected failure (``FootyError`` or ``D1Error``) becomes
a result with an exit code, never a traceback; if the database is the problem the failed-job write
may fail too and must not hide the original error.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from footy.errors import ExitCode, FootyError
from footy.repo.d1_client import D1Error
from footy.repo.ops import OpsRepo

log = logging.getLogger("footy.jobs")

# The workflow timeout is 45 minutes (section 9.3); a row still 'running' after this is dead.
STALE_JOB_MINUTES = 60


@dataclass
class JobResult:
    exit_code: ExitCode
    summary: dict[str, object] = field(default_factory=dict)


def run_job(
    ops: OpsRepo,
    kind: str,
    *,
    now: Callable[[], str],
    git_sha: str | None,
    summary: dict[str, object],
    body: Callable[[], ExitCode],
) -> JobResult:
    """Record ``kind`` in ``job_runs``, run ``body`` (which fills ``summary`` and returns its exit
    code) and record the outcome. Rows left ``running`` by a killed job are closed first."""
    try:
        ops.fail_stale_jobs(now(), STALE_JOB_MINUTES)
        job_id = ops.start_job(kind, now(), git_sha)
    except D1Error as exc:
        return JobResult(ExitCode.UNEXPECTED, {**summary, "error": str(exc)})
    try:
        code = body()
    except (FootyError, D1Error) as exc:
        try:
            ops.finish_job(job_id, now(), "failed", summary, error=str(exc))
        except D1Error:
            log.warning("could not record the failed job in the database")
        exit_code = exc.exit_code if isinstance(exc, FootyError) else ExitCode.UNEXPECTED
        return JobResult(exit_code, {**summary, "error": str(exc)})
    ops.finish_job(job_id, now(), "ok" if code == ExitCode.OK else "partial", summary)
    return JobResult(code, summary)
