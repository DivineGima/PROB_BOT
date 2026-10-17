"""``footy score``: settle pending predictions against stored results (architecture section 8.7).

Idempotent by construction: every update is guarded by ``status = 'pending'``, so running it twice,
or after a partial failure, changes nothing that is already settled. Orchestration only: the rule is
in ``footy.score.settle``, SQL in ``footy.repo.predictions``.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable

from footy.alerts import raise_alert
from footy.clock import utc_now
from footy.errors import ExitCode
from footy.jobs import JobResult, run_job
from footy.repo.ops import OpsRepo
from footy.repo.ports import Database
from footy.repo.predictions import PredictionsRepo
from footy.score.settle import parse_instant, settle
from footy.score.types import NO_RESULT, PENDING, SCORED, VOID

log = logging.getLogger("footy.score")

MAX_LISTED = 20  # fixtures named in the NO_RESULT alert


def run_score_job(
    db: Database,
    *,
    now: Callable[[], str] = utc_now,
    git_sha: str | None = None,
) -> JobResult:
    ops = OpsRepo(db)
    summary: dict[str, object] = {"mode": "score"}

    def body() -> ExitCode:
        at = now()
        moment = parse_instant(at)
        if moment is None:  # an injected clock that is not a timestamp is a programming error
            raise ValueError(f"not a timestamp: {at!r}")
        repo = PredictionsRepo(db)
        pending = repo.pending_with_matches()
        settlements = [settle(p, moment) for p in pending]
        repo.apply(settlements, at)

        voids = Counter(s.void_reason for s in settlements if s.action == VOID)
        unreadable = [s.pred_id for s in settlements if s.action == PENDING and s.note]
        summary.update(
            {
                "pending_before": len(pending),
                "scored": sum(1 for s in settlements if s.action == SCORED),
                "voided": dict(sorted((str(k), v) for k, v in voids.items())),
                "still_pending": sum(1 for s in settlements if s.action == PENDING),
                "unreadable": unreadable,
                "status_counts": repo.counts_by_status(),
            }
        )
        if voids.get(NO_RESULT):
            keys = sorted(
                p.fixture_key
                for p, s in zip(pending, settlements, strict=True)
                if s.void_reason == NO_RESULT
            )
            raise_alert(
                ops,
                at,
                f"no_result:{at[:10]}",
                "no_result_voided",
                {"count": len(keys), "fixtures": keys[:MAX_LISTED]},
            )
        if unreadable:
            raise_alert(
                ops,
                at,
                f"score_unreadable:{at[:10]}",
                "score_unreadable",
                {"pred_ids": unreadable[:MAX_LISTED]},
            )
        return ExitCode.OK

    return run_job(ops, "score", now=now, git_sha=git_sha, summary=summary, body=body)
