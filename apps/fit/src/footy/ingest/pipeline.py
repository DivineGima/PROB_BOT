"""The Stage 2 jobs: ``bootstrap`` (seed + history) and ``ingest`` (nightly window).

Orchestration only: SQL is in ``footy.repo``, HTTP in ``footy.ingest.fd_org``, rules in
``footy.reconcile``. Every job returns a ``JobResult`` whose ``summary`` is safe to print (no
tokens, no raw payloads) and is also stored in ``job_runs.summary_json``.

Failure policy (section 9.4):

* a source outage on one competition does not stop the others; stored data is kept and the job
  exits with code 3;
* a data problem (rejected request, parse failure, more than ``MAX_DISAGREEMENTS`` changed results)
  exits with code 2; in the disagreement case nothing is written at all;
* a season the free plan does not allow (HTTP 403) is reported, not treated as an error.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from footy.aliases import ReferenceData, Resolver
from footy.clock import utc_now
from footy.config import (
    BOOTSTRAP_SEASONS,
    COMPETITIONS,
    FD_COMPETITIONS,
    INGEST_DAYS_BACK,
    INGEST_DAYS_FORWARD,
    MAX_DISAGREEMENTS,
    SOURCE_FD_ORG,
    Competition,
)
from footy.errors import (
    DataError,
    ExitCode,
    FootyError,
    SourceAuthError,
    SourceOutage,
    SourceRestricted,
)
from footy.ingest.fd_org import FdOrgClient
from footy.ingest.parse import ParseReport, parse_matches, parse_team_names, season_label
from footy.jobs import JobResult
from footy.reconcile.matches import Anomaly, MatchRow, plan_writes, to_row
from footy.repo.d1_client import D1Error, MemoryProgress, Progress, execute_resumable
from footy.repo.matches import MatchesRepo
from footy.repo.ops import OpsRepo
from footy.repo.ports import Database
from footy.repo.reference import ReferenceRepo

log = logging.getLogger("footy.pipeline")


def current_season_start_year(today: date) -> int:
    return today.year if today.month >= 7 else today.year - 1


@dataclass
class _Collected:
    rows: list[MatchRow] = field(default_factory=list)
    unmapped: Counter[str] = field(default_factory=Counter)
    skipped: Counter[str] = field(default_factory=Counter)
    anomalies: list[Anomaly] = field(default_factory=list)
    per_request: list[dict[str, object]] = field(default_factory=list)
    outages: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


def _collect(
    collected: _Collected,
    comp: Competition,
    label: str,
    report: ParseReport,
    resolver: Resolver,
) -> None:
    """Resolve names and build rows for one parsed response; unmapped names are counted."""
    built = 0
    unmapped_matches = 0
    for raw in report.matches:
        home = resolver.resolve(raw.home_name)
        away = resolver.resolve(raw.away_name)
        if home is None or away is None:
            unmapped_matches += 1
            if home is None:
                collected.unmapped[raw.home_name] += 1
            if away is None:
                collected.unmapped[raw.away_name] += 1
            continue
        row, anomalies = to_row(raw, int(home), int(away))
        collected.anomalies.extend(anomalies)
        if row is not None:
            collected.rows.append(row)
            built += 1
    for reason, count in report.skipped.items():
        collected.skipped[reason] += count
    collected.per_request.append(
        {
            "competition": comp.comp_code,
            "request": label,
            "received": len(report.matches) + sum(report.skipped.values()),
            "usable": built,
            "skipped_unmapped": unmapped_matches,
            "skipped_invalid": sum(report.skipped.values()),
        }
    )


def _fd_code(comp: Competition) -> str:
    if comp.fd_code is None:
        raise DataError(f"{comp.comp_code} has no football-data.org code")
    return comp.fd_code


def _fetch_matches(
    collected: _Collected,
    client: FdOrgClient,
    comp: Competition,
    resolver: Resolver,
    *,
    label: str,
    date_from: str | None = None,
    date_to: str | None = None,
    season: int | None = None,
) -> str:
    """One paced request. Returns 'ok', 'restricted', 'outage' or 'failed'; never raises on
    source problems except an auth error, which stops the whole job."""
    fd_code = _fd_code(comp)
    try:
        fetched = client.matches(fd_code, date_from=date_from, date_to=date_to, season=season)
    except SourceRestricted:
        collected.per_request.append(
            {"competition": comp.comp_code, "request": label, "restricted": True}
        )
        return "restricted"
    except SourceOutage as exc:
        collected.outages.append(f"{comp.comp_code} {label}: {exc}")
        return "outage"
    except SourceAuthError:
        raise
    except DataError as exc:
        collected.failures.append(f"{comp.comp_code} {label}: {exc}")
        return "failed"
    report = parse_matches(fetched.payload, comp.comp_code)
    if not report.matches and report.skipped.get("payload_shape"):
        collected.failures.append(f"{comp.comp_code} {label}: unexpected payload shape")
        return "failed"
    _collect(collected, comp, label, report, resolver)
    return "ok"


def _unmapped_events(ops: OpsRepo, at: str, unmapped: Counter[str], origin: str) -> None:
    for name, count in sorted(unmapped.items()):
        ops.record_event(
            at,
            "warn",
            SOURCE_FD_ORG,
            "unmapped_team",
            {"name": name, "matches_skipped": count, "origin": origin},
            dedupe_key=f"unmapped:{SOURCE_FD_ORG}:{name.lower()}",
        )


def _anomaly_key(anomaly: Anomaly) -> str:
    ids = anomaly.detail.get("fd_match_ids")
    ident = (
        ",".join(str(i) for i in ids)
        if isinstance(ids, list)
        else anomaly.detail.get("fd_match_id")
    )
    return f"anomaly:{anomaly.kind}:{ident}"


def _anomaly_events(ops: OpsRepo, at: str, anomalies: Sequence[Anomaly]) -> None:
    """One event per anomaly per 24 h: a problem that stays inside the nightly window is not
    re-reported on every run (section 9.2)."""
    for anomaly in anomalies:
        ops.record_event(
            at,
            "warn",
            SOURCE_FD_ORG,
            f"anomaly_{anomaly.kind}",
            anomaly.detail,
            dedupe_key=_anomaly_key(anomaly),
        )


def _fail_job(
    ops: OpsRepo | None,
    job_id: int | None,
    client: FdOrgClient,
    summary: dict[str, object],
    exc: Exception,
    now: Callable[[], str],
) -> None:
    """Best effort: record the failure and the fetch audit trail. If the database itself is the
    problem these writes may fail too; that must not hide the original error."""
    if ops is None or job_id is None:
        return
    try:
        ops.log_fetches(SOURCE_FD_ORG, client.fetches)
        ops.finish_job(job_id, now(), "failed", summary, error=str(exc))
    except D1Error:
        log.warning("could not record the failed job in the database")


def _exit_code_of(exc: Exception) -> ExitCode:
    return exc.exit_code if isinstance(exc, FootyError) else ExitCode.UNEXPECTED


def _exit_code(collected: _Collected) -> ExitCode:
    if collected.failures:
        return ExitCode.DATA
    if collected.outages:
        return ExitCode.SOURCE_OUTAGE
    return ExitCode.OK


def _base_summary(collected: _Collected) -> dict[str, object]:
    return {
        "requests": collected.per_request,
        "unmapped_teams": dict(sorted(collected.unmapped.items())),
        "skipped_invalid_records": dict(collected.skipped),
        "anomalies": dict(Counter(a.kind for a in collected.anomalies)),
        "outages": collected.outages,
        "failures": collected.failures,
    }


# -- seeding -------------------------------------------------------------------------------------


def seed_reference(
    db: Database, ref: ReferenceData, progress: Progress, *, job: str = "seed"
) -> dict[str, int]:
    """Competitions, teams and aliases, in chunked idempotent statements."""
    repo = ReferenceRepo(db)
    execute_resumable(
        db, f"{job}-competitions", repo.competition_statements(COMPETITIONS), progress
    )
    execute_resumable(
        db,
        f"{job}-teams",
        repo.team_statements(
            (t.canonical_name, t.home_comp, t.is_ucl_only, t.active) for t in ref.teams
        ),
        progress,
    )
    ids = repo.team_ids()
    alias_rows: list[tuple[str, str, int]] = []
    for source, table in sorted(ref.aliases.items()):
        for alias_norm, canonical in sorted(table.items()):
            if canonical not in ids:
                raise DataError(
                    "the progress file does not match the database (teams are missing): "
                    "delete the progress file and run bootstrap again"
                )
            alias_rows.append((source, alias_norm, ids[canonical]))
    execute_resumable(db, f"{job}-aliases", repo.alias_statements(alias_rows), progress)
    return repo.counts()


# -- bootstrap -----------------------------------------------------------------------------------


def run_bootstrap(
    client: FdOrgClient,
    ref: ReferenceData,
    *,
    db: Database | None,
    today: date,
    seasons: Sequence[int] | None = None,
    progress: Progress | None = None,
    now: Callable[[], str] = utc_now,
    git_sha: str | None = None,
) -> JobResult:
    """Seed reference data and load history. ``db=None`` is the dry run: it fetches, parses and
    resolves names from the local files, writes nothing and reports history depth and unmapped
    names."""
    start_year = current_season_start_year(today)
    wanted = list(seasons) if seasons else [start_year - i for i in range(BOOTSTRAP_SEASONS)]
    progress = progress if progress is not None else MemoryProgress()
    ops = OpsRepo(db) if db is not None else None
    job_id = ops.start_job("bootstrap", now(), git_sha) if ops is not None else None
    summary: dict[str, object] = {"mode": "dry-run" if db is None else "bootstrap"}
    collected = _Collected()
    try:
        if db is not None:
            summary["seeded"] = seed_reference(db, ref, progress)
            resolver = Resolver(SOURCE_FD_ORG, ReferenceRepo(db).alias_table(SOURCE_FD_ORG))
        else:
            pseudo = {t.canonical_name: i for i, t in enumerate(ref.teams, start=1)}
            resolver = Resolver(
                SOURCE_FD_ORG, {k: pseudo[v] for k, v in ref.aliases[SOURCE_FD_ORG].items()}
            )

        depth: dict[str, dict[str, str]] = {}
        for comp in FD_COMPETITIONS:
            for year in wanted:
                label = season_label(year)
                outcome = _fetch_matches(
                    collected, client, comp, resolver, label=f"season {label}", season=year
                )
                depth.setdefault(comp.comp_code, {})[label] = outcome
        summary["history_depth"] = depth
        summary["history_available_seasons"] = sorted(
            {label for per in depth.values() for label, o in per.items() if o == "ok"}
        )

        if db is not None and ops is not None:
            summary.update(_write_matches(db, collected, progress, now))
            ops.log_fetches(SOURCE_FD_ORG, client.fetches)
            _unmapped_events(ops, now(), collected.unmapped, "bootstrap")
            _anomaly_events(ops, now(), collected.anomalies)
    except (FootyError, D1Error) as exc:
        summary.update(_base_summary(collected))
        _fail_job(ops, job_id, client, summary, exc, now)
        return JobResult(_exit_code_of(exc), {**summary, "error": str(exc)})

    summary.update(_base_summary(collected))
    code = _exit_code(collected)
    if ops is not None and job_id is not None:
        ops.finish_job(job_id, now(), "ok" if code == ExitCode.OK else "partial", summary)
    return JobResult(code, summary)


def _write_matches(
    db: Database, collected: _Collected, progress: Progress, now: Callable[[], str]
) -> dict[str, object]:
    repo = MatchesRepo(db)
    pairs = {(r.comp_code, r.season) for r in collected.rows}
    plan = plan_writes(collected.rows, repo.load_existing(pairs) if pairs else [])
    collected.anomalies.extend(plan.anomalies)
    if len(plan.disagreements) > MAX_DISAGREEMENTS:
        raise DataError(
            f"{len(plan.disagreements)} stored results differ from the source "
            f"(limit {MAX_DISAGREEMENTS}): a parsing or mapping bug is likely; nothing was written"
        )
    rows = plan.to_write + [new for new, _old in plan.disagreements]
    for new, old in plan.disagreements:
        collected.anomalies.append(
            Anomaly(
                "result_changed",
                {
                    "fd_match_id": new.fd_match_id,
                    "was": [old.goals_home, old.goals_away],
                    "now": [new.goals_home, new.goals_away],
                },
            )
        )
    statements = MatchesRepo.upsert_statements(rows, now())
    run = execute_resumable(db, "matches", statements, progress)
    return {
        "matches_inserted": plan.inserted,
        "matches_updated": plan.updated + len(plan.disagreements),
        "matches_unchanged": plan.unchanged,
        "result_changes": len(plan.disagreements),
        "requests_sent": run.requests_sent,
        "requests_skipped_resumed": run.requests_skipped,
    }


# -- nightly ingest ------------------------------------------------------------------------------


def run_ingest(
    client: FdOrgClient,
    *,
    db: Database,
    today: date,
    check_team_lists: bool = True,
    now: Callable[[], str] = utc_now,
    git_sha: str | None = None,
) -> JobResult:
    """Incremental window (today-7 .. today+3), reconcile, upsert, freshness, rollover check."""
    ops = OpsRepo(db)
    job_id = ops.start_job("ingest", now(), git_sha)
    summary: dict[str, object] = {"mode": "ingest"}
    collected = _Collected()
    window_from = (today - timedelta(days=INGEST_DAYS_BACK)).isoformat()
    window_to = (today + timedelta(days=INGEST_DAYS_FORWARD)).isoformat()
    summary["window"] = [window_from, window_to]
    try:
        reference = ReferenceRepo(db)
        if reference.counts()["teams_active"] == 0:
            raise DataError("no teams in the database: run `footy bootstrap` first")
        resolver = Resolver(SOURCE_FD_ORG, reference.alias_table(SOURCE_FD_ORG))

        for comp in FD_COMPETITIONS:
            outcome = _fetch_matches(
                collected,
                client,
                comp,
                resolver,
                label=f"{window_from}..{window_to}",
                date_from=window_from,
                date_to=window_to,
            )
            if outcome == "restricted":
                collected.failures.append(
                    f"{comp.comp_code}: the free plan does not allow the nightly window"
                )
        summary.update(_write_matches(db, collected, MemoryProgress(), now))

        if check_team_lists:
            summary["team_list_check"] = _check_team_lists(client, ops, resolver, now(), collected)

        ops.log_fetches(SOURCE_FD_ORG, client.fetches)
        _unmapped_events(ops, now(), collected.unmapped, "ingest")
        _anomaly_events(ops, now(), collected.anomalies)
        summary["freshness"] = MatchesRepo(db).freshness()
    except (FootyError, D1Error) as exc:
        summary.update(_base_summary(collected))
        _fail_job(ops, job_id, client, summary, exc, now)
        return JobResult(_exit_code_of(exc), {**summary, "error": str(exc)})

    summary.update(_base_summary(collected))
    code = _exit_code(collected)
    ops.finish_job(job_id, now(), "ok" if code == ExitCode.OK else "partial", summary)
    return JobResult(code, summary)


def _check_team_lists(
    client: FdOrgClient, ops: OpsRepo, resolver: Resolver, at: str, collected: _Collected
) -> dict[str, object]:
    """Season rollover (section 8.5): a club in the source's team list that does not resolve means
    the canonical list needs its summer update."""
    out: dict[str, object] = {}
    for comp in FD_COMPETITIONS:
        try:
            fetched = client.teams(_fd_code(comp))
        except SourceOutage as exc:
            collected.outages.append(f"{comp.comp_code} team list: {exc}")
            out[comp.comp_code] = "outage"
            continue
        except SourceRestricted:
            out[comp.comp_code] = "restricted"
            continue
        except SourceAuthError:
            raise
        except DataError as exc:
            collected.failures.append(f"{comp.comp_code} team list: {exc}")
            out[comp.comp_code] = "failed"
            continue
        names = parse_team_names(fetched.payload)
        if names is None:
            collected.failures.append(f"{comp.comp_code} team list: unexpected payload shape")
            out[comp.comp_code] = "failed"
            continue
        missing = sorted(n for n in names if resolver.resolve(n) is None)
        for name in missing:
            ops.record_event(
                at,
                "warn",
                SOURCE_FD_ORG,
                "canonical_update_needed",
                {"competition": comp.comp_code, "name": name},
                dedupe_key=f"rollover:{comp.comp_code}:{name.lower()}",
            )
        out[comp.comp_code] = {"teams": len(names), "unresolved": missing}
    return out


def default_progress_path() -> Path:
    return Path(".footy") / "bootstrap-progress.json"
