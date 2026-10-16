"""``footy`` command line (architecture section 6.7). Stage 2 provides ``bootstrap`` and ``ingest``,
Stage 3 adds ``backtest``; the other commands in the table arrive with their stages.

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

from footy.aliases import load_reference
from footy.backtest.job import DEFAULT_FOLD_DAYS, DEFAULT_TEST_DAYS, run_backtest_job
from footy.config import MIN_REQUEST_INTERVAL_S, Settings, load_settings
from footy.errors import ConfigError, ExitCode, FootyError
from footy.ingest.fd_org import FdOrgClient
from footy.ingest.pacer import Pacer
from footy.ingest.pipeline import (
    JobResult,
    current_season_start_year,
    default_progress_path,
    run_bootstrap,
    run_ingest,
)
from footy.models.registry import FITTERS
from footy.repo.d1_client import D1Client, D1Error, JsonFileProgress, MemoryProgress, Progress
from footy.repo.ports import Database

ClientFactory = Callable[[str], FdOrgClient]
DatabaseFactory = Callable[[Settings], Database]


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
    return parser


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
    models = [m.strip() for m in str(args.models).split(",") if m.strip()]
    unknown = [m for m in models if m not in FITTERS]
    if not models or unknown:
        raise ConfigError(f"unknown model(s) {unknown or args.models!r}; known: {sorted(FITTERS)}")
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
    )


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
