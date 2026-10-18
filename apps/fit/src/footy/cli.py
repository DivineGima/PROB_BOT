"""``footy`` command line (architecture section 6.7). Stage 2 provides ``bootstrap`` and ``ingest``,
Stage 3 adds ``backtest``, Stage 4 adds ``fit`` and ``publish``, Stage 6 adds ``score`` and
``report``, Stage 7 adds ``healthcheck`` and ``alert``.

Exit codes: 0 ok, 1 unexpected, 2 data/validation failure, 3 source outage, 4 fit failure.
The summary printed on stdout never contains tokens or raw source payloads.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from footy.alerts.deliver import alert_with_text, flush_alerts
from footy.aliases import load_reference
from footy.backtest.job import DEFAULT_FOLD_DAYS, DEFAULT_TEST_DAYS, run_backtest_job
from footy.config import (
    BACKTEST_REGRESSION_TOLERANCE,
    MIN_REQUEST_INTERVAL_S,
    Settings,
    load_settings,
)
from footy.errors import ConfigError, ExitCode, FootyError
from footy.fitting import run_fit_job
from footy.health import run_healthcheck_job
from footy.ingest.fd_org import FdOrgClient
from footy.ingest.pacer import Pacer
from footy.ingest.pipeline import (
    current_season_start_year,
    default_progress_path,
    run_bootstrap,
    run_ingest,
)
from footy.jobs import JobResult
from footy.models.registry import FITTERS
from footy.models.types import MODELS
from footy.publish.job import run_publish_job
from footy.repo.d1_client import D1Client, D1Error, JsonFileProgress, MemoryProgress, Progress
from footy.repo.ops import OpsRepo
from footy.repo.ports import Database
from footy.report.job import run_report_job
from footy.score.job import run_score_job
from footy.telegram import TelegramSender

ClientFactory = Callable[[str], FdOrgClient]
DatabaseFactory = Callable[[Settings], Database]
SenderFactory = Callable[[str, str], TelegramSender]


def _default_sender(token: str, chat_id: str) -> TelegramSender:
    return TelegramSender(token, chat_id)


def _default_client(token: str) -> FdOrgClient:
    return FdOrgClient(token, pacer=Pacer(MIN_REQUEST_INTERVAL_S))


def _default_database(settings: Settings) -> Database:
    account, database, token = settings.require_d1()
    return D1Client(account, database, token)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="footy", description="Football probability bot fit job")
    sub = parser.add_subparsers(dest="command", required=True)

    boot = sub.add_parser(
        "bootstrap",
        help="seed teams and aliases, then load the last seasons from football-data.org",
    )
    boot.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch and resolve names but write nothing (needs no database); reports history depth",
    )
    boot.add_argument(
        "--seasons",
        type=int,
        default=None,
        help="number of seasons to load, newest first (default 3)",
    )
    boot.add_argument(
        "--progress-file",
        type=Path,
        default=None,
        help="local JSON file that makes an interrupted bootstrap resumable",
    )

    ingest = sub.add_parser("ingest", help="incremental fetch: today-7 .. today+3")
    ingest.add_argument(
        "--skip-team-check", action="store_true", help="skip the season-rollover team-list check"
    )

    back = sub.add_parser(
        "backtest",
        help="walk-forward evaluation of the models against the league-frequency baseline",
    )
    back.add_argument("--models", default="dc", help="comma-separated model names (default dc)")
    back.add_argument(
        "--test-days",
        type=int,
        default=DEFAULT_TEST_DAYS,
        help="length of the test period, ending at the latest stored result",
    )
    back.add_argument("--fold-days", type=int, default=DEFAULT_FOLD_DAYS, help="days per fold")
    back.add_argument(
        "--half-lives", default=None, help="comma-separated time-decay half-lives to sweep (days)"
    )
    back.add_argument(
        "--shrinks", default=None, help="comma-separated team shrinkage strengths to sweep"
    )
    back.add_argument(
        "--out", type=Path, default=None, help="also write the text report to this file"
    )
    back.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="exit 4 when a model's RPS is worse than in the previous comparable backtest by more "
        "than the tolerance (informational: it never blocks a deploy)",
    )
    back.add_argument(
        "--regression-tolerance",
        type=float,
        default=BACKTEST_REGRESSION_TOLERANCE,
        help="largest tolerated RPS rise versus the previous comparable backtest",
    )

    fit = sub.add_parser(
        "fit",
        help="fit dc / pi / bp, weight the ensemble, snapshot team form; writes a building run",
    )
    fit.add_argument("--models", default=",".join(MODELS), help="comma-separated model names")
    fit.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        help="YYYY-MM-DD; window and time decay end here (default: the latest stored result)",
    )

    sub.add_parser("score", help="settle pending predictions against stored results")

    report = sub.add_parser(
        "report", help="weekly calibration summary; stores a snapshot and can send it to Telegram"
    )
    report.add_argument(
        "--send", action="store_true", help="send the text and chart to Telegram (needs the token)"
    )
    report.add_argument(
        "--monday-only", action="store_true", help="do nothing unless today (UTC) is a Monday"
    )

    sub.add_parser(
        "healthcheck",
        help="is the system doing its job? raises an alert event per failed check; exit 1 if any",
    )

    alert = sub.add_parser(
        "alert",
        help="send alerts to Telegram: the pending alert events, or a text (workflow failure)",
    )
    what = alert.add_mutually_exclusive_group(required=True)
    what.add_argument(
        "--flush", action="store_true", help="send every alert event that was not sent yet"
    )
    what.add_argument(
        "--text", default=None, help="send this text as an alert (used when a workflow fails)"
    )
    alert.add_argument(
        "--key",
        default=None,
        help="with --text: dedupe key (default: the text), at most one alert per key a day",
    )

    publish = sub.add_parser(
        "publish", help="run the promotion gate and make a built run active (or roll back)"
    )
    publish.add_argument(
        "--run-id", default=None, help="run to publish (default: the newest 'building' run)"
    )
    publish.add_argument(
        "--rollback",
        default=None,
        metavar="RUN_ID",
        help="point the active run back at a retained 'superseded' run (no gate)",
    )
    publish.add_argument(
        "--accept-drift",
        action="store_true",
        help="with --run-id only: skip the stability guard for that run after a human decided "
        "a large parameter move is real; other gate checks still apply; the override is logged",
    )
    return parser


def _models_arg(raw: str) -> list[str]:
    models = [m.strip() for m in str(raw).split(",") if m.strip()]
    unknown = [m for m in models if m not in FITTERS]
    if not models or unknown:
        raise ConfigError(f"unknown model(s) {unknown or raw!r}; known: {sorted(FITTERS)}")
    return models


def _float_list(raw: str | None, name: str) -> list[float] | None:
    if raw is None:
        return None
    try:
        values = [float(part) for part in raw.split(",") if part.strip()]
    except ValueError:
        raise ConfigError(f"{name} must be a comma-separated list of numbers") from None
    if not values or any(v <= 0 for v in values):
        raise ConfigError(f"{name} must hold positive numbers")
    return values


def _run_backtest(
    args: argparse.Namespace,
    settings: Settings,
    database_factory: DatabaseFactory,
    git_sha: str | None,
) -> JobResult:
    models = _models_arg(args.models)
    half_lives = _float_list(args.half_lives, "--half-lives")
    shrinks = _float_list(args.shrinks, "--shrinks")
    out: Path | None = args.out

    def sink(text: str) -> None:
        print(text, file=sys.stderr)  # the readable report goes to the log, JSON to stdout
        if out is not None:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text + "\n", encoding="utf-8")

    return run_backtest_job(
        database_factory(settings),
        models=models,
        test_days=args.test_days,
        fold_days=args.fold_days,
        half_lives=half_lives,
        shrinks=shrinks,
        git_sha=git_sha,
        report_sink=sink,
        fail_on_regression=bool(args.fail_on_regression),
        regression_tolerance=float(args.regression_tolerance),
    )


def _run_alert(
    args: argparse.Namespace,
    settings: Settings,
    database_factory: DatabaseFactory,
    sender_factory: SenderFactory,
) -> JobResult:
    """``alert --flush`` needs the database; ``alert --text`` runs when a workflow failed, often
    because the database was the problem, so it falls back to sending the text directly."""
    token, chat_id = settings.require_telegram()
    sender = sender_factory(token, chat_id)
    at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if args.flush:
        flushed = flush_alerts(OpsRepo(database_factory(settings)), sender, at)
        return JobResult(ExitCode.OK, {"mode": "alert-flush", **vars(flushed)})
    ops: OpsRepo | None = None
    try:
        ops = OpsRepo(database_factory(settings))
    except FootyError:  # the database settings are missing: still tell Divine
        ops = None
    key = args.key or args.text[:120]
    sent = alert_with_text(ops, sender, at, key, args.text)
    return JobResult(ExitCode.OK, {"mode": "alert-text", "sent": sent})


def _progress(path: Path | None, dry_run: bool) -> Progress:
    if dry_run:
        return MemoryProgress()
    return JsonFileProgress(path if path is not None else default_progress_path())


def _run_data_command(
    args: argparse.Namespace,
    settings: Settings,
    client_factory: ClientFactory,
    database_factory: DatabaseFactory,
    today: date | None,
    git_sha: str | None,
) -> JobResult:
    token = settings.require_fd_org()  # the legal gate: refuses unless the flag is on
    client = client_factory(token)
    day = today if today is not None else datetime.now(UTC).date()
    if args.command == "bootstrap":
        if args.seasons is not None and not 1 <= args.seasons <= 10:
            raise ConfigError("--seasons must be between 1 and 10")
        reference = load_reference()  # only bootstrap needs the local team files
        db = None if args.dry_run else database_factory(settings)
        seasons = None
        if args.seasons is not None:
            start = current_season_start_year(day)
            seasons = [start - i for i in range(args.seasons)]
        return run_bootstrap(
            client,
            reference,
            db=db,
            today=day,
            seasons=seasons,
            progress=_progress(args.progress_file, args.dry_run),
            git_sha=git_sha,
        )
    return run_ingest(
        client,
        db=database_factory(settings),
        today=day,
        check_team_lists=not args.skip_team_check,
        git_sha=git_sha,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    client_factory: ClientFactory = _default_client,
    database_factory: DatabaseFactory = _default_database,
    sender_factory: SenderFactory = _default_sender,
    today: date | None = None,
) -> int:
    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s"
    )
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(env)
        git_sha = (os.environ if env is None else env).get("GITHUB_SHA")
        result: JobResult
        if args.command == "backtest":
            # model commands need only the database, not football-data.org
            result = _run_backtest(args, settings, database_factory, git_sha)
        elif args.command == "fit":
            result = run_fit_job(
                database_factory(settings),
                models=_models_arg(args.models),
                as_of=args.as_of,
                git_sha=git_sha,
            )
        elif args.command == "score":
            result = run_score_job(database_factory(settings), git_sha=git_sha)
        elif args.command == "report":
            sender = None
            if args.send:
                token, chat_id = settings.require_telegram()
                sender = sender_factory(token, chat_id)
            result = run_report_job(
                database_factory(settings),
                sender=sender,
                send=bool(args.send),
                monday_only=bool(args.monday_only),
                git_sha=git_sha,
            )
        elif args.command == "healthcheck":
            result = run_healthcheck_job(database_factory(settings), git_sha=git_sha)
        elif args.command == "alert":
            result = _run_alert(args, settings, database_factory, sender_factory)
        elif args.command == "publish":
            if args.run_id and args.rollback:
                raise ConfigError("use either --run-id or --rollback, not both")
            result = run_publish_job(
                database_factory(settings),
                run_id=args.run_id,
                rollback=args.rollback,
                accept_drift=args.accept_drift,
                git_sha=git_sha,
            )
        else:
            result = _run_data_command(
                args, settings, client_factory, database_factory, today, git_sha
            )
    except FootyError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stdout)
        return int(exc.exit_code)
    except D1Error as exc:  # messages never contain the token or request bodies
        print(json.dumps({"error": str(exc)}), file=sys.stdout)
        return int(ExitCode.UNEXPECTED)
    except Exception as exc:  # last resort: never print a traceback that could echo a request
        print(json.dumps({"error": f"unexpected {type(exc).__name__}"}), file=sys.stdout)
        logging.getLogger("footy").exception("unexpected failure")
        return int(ExitCode.UNEXPECTED)

    print(json.dumps(result.summary, sort_keys=True, default=str))
    return int(result.exit_code)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
