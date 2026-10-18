"""``footy healthcheck`` (architecture sections 9.2 and 10, NFR-08): is the system doing its job?

Silent failure is a defect, so the nightly job ends by asking the database five questions. Each is a
``Check``; every failed check becomes a deduplicated alert event, which the delivery step sends.
The Worker's own watchdog asks the first, second and fourth question again every six hours, which
catches the case where the nightly workflow never ran at all (ADR-015, ADR-029).

1. ``active_run``: a model run is published.
2. ``run_age``: it was activated at most ``STALE_HOURS`` ago.
3. ``forecast_coverage``: for today and tomorrow, every day that has scheduled fixtures has
   forecasts in the active run (without them every match is answered ``NO_FORECAST``).
4. ``stuck_uploads``: no upload was acknowledged and left unanswered for over ten minutes.
5. ``bot_token``: in the last 24 h the Worker has not reported that it cannot speak: a missing
   bot token, a token Telegram refused, an unusable chat id or a watchdog crash (it then cannot
   reply or alert, so this side must). The report ends 24 h after the cause is fixed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from footy.alerts import raise_alert
from footy.config import HEALTH_FORECAST_DAYS, STALE_HOURS, STUCK_UPLOAD_MINUTES
from footy.errors import ExitCode
from footy.jobs import JobResult, run_job
from footy.repo.health import HealthRepo
from footy.repo.ops import OpsRepo
from footy.repo.ports import Database

_TS = "%Y-%m-%dT%H:%M:%SZ"
TOKEN_LOOKBACK_HOURS = 24
# What the Worker writes when it cannot reply or alert (upload, usage hint and watchdog paths).
BOT_PROBLEM_KINDS = (
    "bot_token_missing",
    "alert_chat_invalid",
    "alert_send_failed",
    "watchdog_failed",
)


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _parse(at: str) -> datetime | None:
    try:
        return datetime.strptime(at, _TS).replace(tzinfo=UTC)
    except ValueError:
        return None


def run_checks(repo: HealthRepo, now: datetime) -> list[Check]:
    """Pure over the repository: the five checks at the moment ``now`` (UTC)."""
    checks: list[Check] = []
    active = repo.active_run()
    if active is None:
        checks.append(Check("active_run", False, "no model run is published"))
    else:
        checks.append(Check("active_run", True, active.run_id))
        activated = _parse(active.activated_at)
        if activated is None:
            checks.append(Check("run_age", False, "the activation time cannot be read"))
        else:
            age_h = (now - activated).total_seconds() / 3600
            limit = active.stale_hours or STALE_HOURS  # the run's own limit, as the Worker uses
            checks.append(
                Check(
                    "run_age",
                    age_h <= limit,
                    f"active run is {age_h:.0f} h old (limit {limit:g} h)",
                )
            )

    if active is None:
        checks.append(Check("forecast_coverage", False, "no active run to hold forecasts"))
    else:
        missing: list[str] = []
        checked = 0
        for offset in range(HEALTH_FORECAST_DAYS):
            day = (now + timedelta(days=offset)).date().isoformat()
            scheduled = repo.scheduled_count(day)
            if scheduled == 0:
                continue  # nothing to forecast that day
            checked += 1
            if repo.forecast_count(active.run_id, day) == 0:
                missing.append(f"{day} ({scheduled} scheduled)")
        if missing:
            checks.append(
                Check(
                    "forecast_coverage",
                    False,
                    "no forecasts stored for " + ", ".join(missing) + "; run fit and publish",
                )
            )
        else:
            checks.append(
                Check("forecast_coverage", True, f"{checked} day(s) with fixtures covered")
            )

    stuck = repo.stuck_uploads((now - timedelta(minutes=STUCK_UPLOAD_MINUTES)).strftime(_TS))
    checks.append(
        Check(
            "stuck_uploads",
            stuck == 0,
            f"{stuck} upload(s) acknowledged but never answered" if stuck else "none",
        )
    )

    since = (now - timedelta(hours=TOKEN_LOOKBACK_HOURS)).strftime(_TS)
    problems = repo.events_since(BOT_PROBLEM_KINDS, since)
    checks.append(
        Check(
            "bot_token",
            problems == 0,
            f"the Worker could not reply or alert ({problems} report(s) in "
            f"{TOKEN_LOOKBACK_HOURS} h): "
            "check TELEGRAM_BOT_TOKEN and ALLOWED_CHAT_ID"
            if problems
            else "ok",
        )
    )
    return checks


def run_healthcheck_job(
    db: Database,
    *,
    git_sha: str | None = None,
    now: Callable[[], str] | None = None,
) -> JobResult:
    """Run the checks, raise an alert event per failure, and exit 1 when anything is unhealthy."""
    clock = now or (lambda: datetime.now(UTC).strftime(_TS))
    ops = OpsRepo(db)
    summary: dict[str, object] = {"mode": "healthcheck"}

    def body() -> ExitCode:
        moment = _parse(clock()) or datetime.now(UTC)
        checks = run_checks(HealthRepo(db), moment)
        summary["checks"] = {c.name: {"ok": c.ok, "detail": c.detail} for c in checks}
        failed = [c for c in checks if not c.ok]
        for c in failed:
            raise_alert(
                ops,
                clock(),
                f"health:{c.name}",
                "health_check_failed",
                {"check": c.name, "detail": c.detail},
            )
        summary["healthy"] = not failed
        return ExitCode.OK if not failed else ExitCode.UNEXPECTED

    return run_job(ops, "healthcheck", now=clock, git_sha=git_sha, summary=summary, body=body)
