"""``footy`` command line (architecture section 6.7). Stage 2 provides ``bootstrap`` and ``ingest``;
the other commands in the table arrive with their stages.

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
    return parser


def _progress(path: Path | None, dry_run: bool) -> Progress:
    if dry_run:
        return MemoryProgress()
    return JsonFileProgress(path if path is not None else default_progress_path())


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
        token = settings.require_fd_org()  # the legal gate: refuses unless the flag is on
        reference = load_reference()
        client = client_factory(token)
        day = today if today is not None else datetime.now(UTC).date()
        git_sha = (os.environ if env is None else env).get("GITHUB_SHA")

        result: JobResult
        if args.command == "bootstrap":
            if args.seasons is not None and not 1 <= args.seasons <= 10:
                raise ConfigError("--seasons must be between 1 and 10")
            db = None if args.dry_run else database_factory(settings)
            seasons = None
            if args.seasons is not None:
                start = current_season_start_year(day)
                seasons = [start - i for i in range(args.seasons)]
            result = run_bootstrap(
                client,
                reference,
                db=db,
                today=day,
                seasons=seasons,
                progress=_progress(args.progress_file, args.dry_run),
                git_sha=git_sha,
            )
        else:
            result = run_ingest(
                client,
                reference,
                db=database_factory(settings),
                today=day,
                check_team_lists=not args.skip_team_check,
                git_sha=git_sha,
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
