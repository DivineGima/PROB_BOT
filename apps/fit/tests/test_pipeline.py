"""End-to-end bootstrap and ingest on synthetic data with a SQLite-backed fake D1 (Stage 2 steps
5 to 7 and exit criteria). Team names are real football-data.org spellings of canonical clubs."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from footy.aliases import load_reference
from footy.errors import ExitCode
from footy.ingest.pipeline import (
    current_season_start_year,
    run_bootstrap,
    run_ingest,
    seed_reference,
)
from footy.repo.d1_client import D1TransientError, JsonFileProgress, MemoryProgress
from footy.repo.reference import ReferenceRepo
from tests.helpers import ScriptedTransport, SqliteD1, fd_match, make_client

TODAY = date(2026, 10, 17)
NOW = "2026-10-17T01:17:00Z"
REF = load_reference()
FD_COMPETITION_CODES = ["PL", "PD", "BL1", "SA", "FL1", "DED", "PPL", "ELC", "CL"]


def season_routes(code: str, matches: list[dict[str, Any]]) -> dict[tuple[str, str], object]:
    return {(code, "season:2025"): {"matches": matches}}


def test_current_season_start_year() -> None:
    assert current_season_start_year(date(2026, 10, 17)) == 2026
    assert current_season_start_year(date(2027, 3, 1)) == 2026
    assert current_season_start_year(date(2027, 7, 1)) == 2027
    assert current_season_start_year(date(2027, 6, 30)) == 2026


# -- bootstrap ------------------------------------------------------------------------------------


def history_routes() -> dict[tuple[str, str], object]:
    routes: dict[tuple[str, str], object] = {}
    routes[("PL", "season:2025")] = {
        "matches": [
            fd_match(1, "Arsenal FC", "Chelsea FC", "2025-08-16T14:00:00Z", full=(2, 1)),
            fd_match(2, "Liverpool FC", "Manchester City FC", "2025-08-23T14:00:00Z", full=(0, 0)),
            fd_match(3, "Atlantis United FC", "Arsenal FC", "2025-08-30T14:00:00Z"),
            fd_match(
                4,
                "Chelsea FC",
                "Liverpool FC",
                "2025-09-06T14:00:00Z",
                duration="EXTRA_TIME",
                full=(3, 2),
            ),
            fd_match(
                5,
                "Arsenal FC",
                "Liverpool FC",
                "2025-09-13T14:00:00Z",
                duration="EXTRA_TIME",
                full=(2, 1),
                regular=(1, 1),
            ),
        ]
    }
    routes[("PD", "season:2025")] = {
        "matches": [
            fd_match(10, "FC Barcelona", "Real Madrid CF", "2025-10-26T19:00:00Z", full=(2, 2))
        ]
    }
    for code in FD_COMPETITION_CODES:
        for year in (2024, 2023):
            routes[(code, f"season:{year}")] = 403  # free plan: current season only
    routes[("PL", "season:2024")] = {
        "matches": [
            fd_match(
                20, "Arsenal FC", "Chelsea FC", "2024-08-17T14:00:00Z", season_start="2024-08-10"
            )
        ]
    }
    return routes


def test_dry_run_reports_history_depth_and_unmapped_without_writing() -> None:
    client = make_client(ScriptedTransport(history_routes()))
    result = run_bootstrap(client, REF, db=None, today=TODAY, now=lambda: NOW)
    s = result.summary
    assert result.exit_code == ExitCode.OK
    assert s["mode"] == "dry-run"
    depth: dict[str, dict[str, str]] = s["history_depth"]  # type: ignore[assignment]
    assert depth["EPL"] == {"2026-27": "ok", "2025-26": "ok", "2024-25": "ok"}
    assert depth["LL"] == {"2026-27": "ok", "2025-26": "ok", "2024-25": "restricted"}
    assert s["unmapped_teams"] == {"Atlantis United FC": 1}
    assert "2025-26" in s["history_available_seasons"]  # type: ignore[operator]
    requests: list[dict[str, Any]] = s["requests"]  # type: ignore[assignment]
    assert any(r.get("restricted") for r in requests)
    assert len(client.fetches) == 9 * 3  # one request per competition and season


def test_bootstrap_loads_history_and_is_idempotent() -> None:
    db = SqliteD1()
    transport = ScriptedTransport(history_routes())
    result = run_bootstrap(make_client(transport), REF, db=db, today=TODAY, now=lambda: NOW)
    assert result.exit_code == ExitCode.OK, result.summary
    s = result.summary
    assert s["seeded"] == {
        "competitions": 10,
        "teams_active": 179,
        "teams_history_only": len(REF.teams) - 179,
        "aliases": sum(len(t) for t in REF.aliases.values()),
    }
    assert s["matches_inserted"] == 6  # PL 2025: 4 usable of 5, PD: 1, PL 2024: 1
    assert db.scalar("SELECT COUNT(*) FROM matches") == s["matches_inserted"]

    ids = ReferenceRepo(db).team_ids()
    rows = {r["fd_match_id"]: r for r in db.rows("SELECT * FROM matches")}
    assert (rows[1]["goals_home"], rows[1]["result_basis"], rows[1]["season"]) == (
        2,
        "ft_90",
        "2025-26",
    )
    assert rows[1]["home_team_id"] == ids["Arsenal"]
    assert (rows[4]["goals_home"], rows[4]["result_basis"]) == (
        None,
        "unverified",
    )  # ET, no regularTime
    assert (rows[5]["goals_home"], rows[5]["goals_away"], rows[5]["result_basis"]) == (
        1,
        1,
        "regular",
    )
    assert rows[20]["season"] == "2024-25"
    assert 3 not in rows  # the Atlantis match is skipped, never guessed

    # bookkeeping
    assert db.scalar("SELECT status FROM job_runs WHERE kind = 'bootstrap'") == "ok"
    assert db.scalar("SELECT COUNT(*) FROM source_fetch_log") == 27
    assert db.scalar("SELECT COUNT(*) FROM source_fetch_log WHERE http_status = 403") == 8
    assert db.scalar("SELECT COUNT(*) FROM events WHERE kind = 'unmapped_team'") == 1

    # running it again changes nothing
    again = run_bootstrap(
        make_client(ScriptedTransport(history_routes())), REF, db=db, today=TODAY, now=lambda: NOW
    )
    assert again.exit_code == ExitCode.OK
    assert again.summary["matches_inserted"] == 0 and again.summary["matches_updated"] == 0
    assert again.summary["matches_unchanged"] == 6
    assert db.scalar("SELECT COUNT(*) FROM matches") == 6
    assert db.scalar("SELECT COUNT(*) FROM events WHERE kind = 'unmapped_team'") == 1  # deduped


def test_bootstrap_resumes_after_a_failure(tmp_path: Path) -> None:
    clean = SqliteD1()
    run_bootstrap(
        make_client(ScriptedTransport(history_routes())),
        REF,
        db=clean,
        today=TODAY,
        now=lambda: NOW,
    )
    full_run_requests = clean.requests

    db = SqliteD1()
    progress_path = tmp_path / "progress.json"
    db.fail_at_request = 6  # part-way through the seed, after some chunks were applied
    with pytest.raises(D1TransientError):
        run_bootstrap(
            make_client(ScriptedTransport(history_routes())),
            REF,
            db=db,
            today=TODAY,
            progress=JsonFileProgress(progress_path),
            now=lambda: NOW,
        )
    assert progress_path.exists()
    requests_before = db.requests
    db.fail_at_request = None
    result = run_bootstrap(
        make_client(ScriptedTransport(history_routes())),
        REF,
        db=db,
        today=TODAY,
        progress=JsonFileProgress(progress_path),
        now=lambda: NOW,
    )
    assert result.exit_code == ExitCode.OK
    assert db.scalar("SELECT COUNT(*) FROM matches") == 6
    assert db.scalar("SELECT COUNT(*) FROM teams WHERE active = 1") == 179
    assert db.scalar("SELECT COUNT(*) FROM team_aliases") == sum(
        len(t) for t in REF.aliases.values()
    )
    # Chunks finished before the failure were not sent again.
    assert db.requests - requests_before < full_run_requests


def test_bootstrap_with_an_outage_keeps_going_and_exits_3() -> None:
    routes = history_routes()
    routes[("SA", "season:2025")] = 500  # Serie A is down; everything else works
    result = run_bootstrap(
        make_client(ScriptedTransport(routes)), REF, db=SqliteD1(), today=TODAY, now=lambda: NOW
    )
    assert result.exit_code == ExitCode.SOURCE_OUTAGE
    assert result.summary["matches_inserted"] == 6
    assert result.summary["outages"]


def test_bootstrap_rejected_token_fails_with_exit_2_and_logs_the_attempt() -> None:
    db = SqliteD1()
    routes = {("PL", "season:2026"): 401}
    result = run_bootstrap(
        make_client(ScriptedTransport(routes)), REF, db=db, today=TODAY, now=lambda: NOW
    )
    assert result.exit_code == ExitCode.DATA
    assert "rejected the token" in str(result.summary["error"])
    assert db.scalar("SELECT status FROM job_runs WHERE kind = 'bootstrap'") == "failed"
    assert db.scalar("SELECT http_status FROM source_fetch_log") == 401


def test_bootstrap_seasons_argument() -> None:
    client = make_client(ScriptedTransport({}))
    result = run_bootstrap(client, REF, db=None, today=TODAY, seasons=[2025], now=lambda: NOW)
    assert len(client.fetches) == 9
    assert result.summary["history_available_seasons"] == ["2025-26"]


# -- ingest ---------------------------------------------------------------------------------------


@pytest.fixture
def seeded() -> SqliteD1:
    db = SqliteD1()
    seed_reference(db, REF, MemoryProgress())
    return db


def window_routes(matches: list[dict[str, Any]], code: str = "PL") -> dict[tuple[str, str], object]:
    return {(code, "window"): {"matches": matches}}


def play(match_id: int, home: str, away: str, day: str, **kw: Any) -> dict[str, Any]:
    return fd_match(match_id, home, away, f"{day}T14:00:00Z", season_start="2026-08-15", **kw)


def ingest(db: SqliteD1, routes: dict[tuple[str, str], object], **kw: Any) -> Any:
    return run_ingest(
        make_client(ScriptedTransport(routes)), REF, db=db, today=TODAY, now=lambda: NOW, **kw
    )


def test_ingest_requires_bootstrap_first() -> None:
    result = ingest(SqliteD1(), {})
    assert result.exit_code == ExitCode.DATA
    assert "footy bootstrap" in str(result.summary["error"])


def test_ingest_inserts_updates_and_is_idempotent(seeded: SqliteD1) -> None:
    scheduled = [
        play(
            1,
            "Arsenal FC",
            "Chelsea FC",
            "2026-10-18",
            status="TIMED",
            duration=None,
            full=(None, None),
        ),
        play(2, "Liverpool FC", "Manchester City FC", "2026-10-12", full=(1, 0)),
    ]
    first = ingest(seeded, window_routes(scheduled))
    assert first.exit_code == ExitCode.OK, first.summary
    assert first.summary["window"] == ["2026-10-10", "2026-10-20"]
    assert (first.summary["matches_inserted"], first.summary["matches_updated"]) == (2, 0)
    assert first.summary["freshness"] == {"EPL": "2026-10-12"}

    second = ingest(seeded, window_routes(scheduled))
    assert (
        second.summary["matches_inserted"],
        second.summary["matches_updated"],
        second.summary["matches_unchanged"],
    ) == (0, 0, 2)

    # the TIMED match is played: it is updated in place, not duplicated
    played = [play(1, "Arsenal FC", "Chelsea FC", "2026-10-18", full=(3, 1)), scheduled[1]]
    third = ingest(seeded, window_routes(played))
    assert (third.summary["matches_inserted"], third.summary["matches_updated"]) == (0, 1)
    row = seeded.rows("SELECT * FROM matches WHERE fd_match_id = 1")[0]
    assert (row["status"], row["goals_home"], row["result_basis"]) == ("FINISHED", 3, "ft_90")
    assert seeded.scalar("SELECT COUNT(*) FROM matches") == 2
    assert seeded.scalar("SELECT status FROM job_runs ORDER BY job_id DESC LIMIT 1") == "ok"
    assert third.summary["freshness"] == {"EPL": "2026-10-18"}


def test_ingest_keeps_finished_matches_final(seeded: SqliteD1) -> None:
    done = [play(1, "Arsenal FC", "Chelsea FC", "2026-10-12", full=(2, 0))]
    ingest(seeded, window_routes(done))
    stale = [
        play(
            1,
            "Arsenal FC",
            "Chelsea FC",
            "2026-10-12",
            status="IN_PLAY",
            duration=None,
            full=(None, None),
        )
    ]
    result = ingest(seeded, window_routes(stale))
    assert result.summary["anomalies"] == {"status_regression": 1}
    assert seeded.scalar("SELECT status FROM matches") == "FINISHED"
    assert (
        seeded.scalar("SELECT COUNT(*) FROM events WHERE kind = 'anomaly_status_regression'") == 1
    )


def test_ingest_handles_a_rescheduled_match(seeded: SqliteD1) -> None:
    ingest(
        seeded,
        window_routes(
            [
                play(
                    1,
                    "Arsenal FC",
                    "Chelsea FC",
                    "2026-10-18",
                    status="SCHEDULED",
                    duration=None,
                    full=(None, None),
                )
            ]
        ),
    )
    moved = play(
        1,
        "Arsenal FC",
        "Chelsea FC",
        "2026-11-04",
        status="POSTPONED",
        duration=None,
        full=(None, None),
    )
    result = ingest(seeded, window_routes([moved]))
    assert result.summary["matches_updated"] == 1
    assert seeded.scalar("SELECT match_date FROM matches") == "2026-11-04"
    assert seeded.scalar("SELECT COUNT(*) FROM matches") == 1


def test_unmapped_teams_are_skipped_reported_and_deduped(seeded: SqliteD1) -> None:
    matches = [
        play(1, "Arsenal FC", "Chelsea FC", "2026-10-12"),
        play(2, "Newtown Rovers FC", "Chelsea FC", "2026-10-13"),
        play(3, "Arsenal FC", "Newtown Rovers FC", "2026-10-14"),
    ]
    result = ingest(seeded, window_routes(matches))
    assert result.exit_code == ExitCode.OK
    assert result.summary["unmapped_teams"] == {"Newtown Rovers FC": 2}
    assert seeded.scalar("SELECT COUNT(*) FROM matches") == 1
    ingest(seeded, window_routes(matches))
    assert seeded.scalar("SELECT COUNT(*) FROM events WHERE kind = 'unmapped_team'") == 1


def test_more_than_three_changed_results_fail_the_run_and_write_nothing(seeded: SqliteD1) -> None:
    original = [
        play(i, "Arsenal FC", "Chelsea FC", f"2026-10-{10 + i:02d}", full=(1, 0))
        for i in range(1, 6)
    ]
    ingest(seeded, window_routes(original))
    flipped = [
        play(i, "Arsenal FC", "Chelsea FC", f"2026-10-{10 + i:02d}", full=(0, 4))
        for i in range(1, 6)
    ]
    result = ingest(seeded, window_routes(flipped))
    assert result.exit_code == ExitCode.DATA
    assert "nothing was written" in str(result.summary["error"])
    assert seeded.scalar("SELECT COUNT(*) FROM matches WHERE goals_home = 1") == 5
    assert seeded.scalar("SELECT status FROM job_runs ORDER BY job_id DESC LIMIT 1") == "failed"


def test_up_to_three_changed_results_are_applied_and_recorded(seeded: SqliteD1) -> None:
    original = [
        play(i, "Arsenal FC", "Chelsea FC", f"2026-10-{10 + i:02d}", full=(1, 0))
        for i in range(1, 4)
    ]
    ingest(seeded, window_routes(original))
    flipped = [
        play(i, "Arsenal FC", "Chelsea FC", f"2026-10-{10 + i:02d}", full=(0, 4))
        for i in range(1, 4)
    ]
    result = ingest(seeded, window_routes(flipped))
    assert result.exit_code == ExitCode.OK
    assert result.summary["result_changes"] == 3
    assert seeded.scalar("SELECT COUNT(*) FROM matches WHERE goals_home = 0") == 3
    assert seeded.scalar("SELECT COUNT(*) FROM events WHERE kind = 'anomaly_result_changed'") == 3


def test_an_outage_in_one_competition_does_not_stop_the_rest(seeded: SqliteD1) -> None:
    routes = window_routes([play(1, "Arsenal FC", "Chelsea FC", "2026-10-12")])
    routes[("PD", "window")] = 503
    result = ingest(seeded, routes)
    assert result.exit_code == ExitCode.SOURCE_OUTAGE
    assert seeded.scalar("SELECT COUNT(*) FROM matches") == 1
    assert seeded.scalar("SELECT status FROM job_runs ORDER BY job_id DESC LIMIT 1") == "partial"
    assert seeded.scalar("SELECT COUNT(*) FROM source_fetch_log WHERE http_status = 503") == 3


def test_a_restricted_nightly_window_is_a_failure(seeded: SqliteD1) -> None:
    result = ingest(seeded, {("ELC", "window"): 403})
    assert result.exit_code == ExitCode.DATA
    assert any("does not allow the nightly window" in f for f in result.summary["failures"])


def test_bad_payload_shape_is_a_data_failure(seeded: SqliteD1) -> None:
    result = ingest(seeded, {("PL", "window"): {"unexpected": True}})
    assert result.exit_code == ExitCode.DATA
    assert seeded.scalar("SELECT COUNT(*) FROM matches") == 0


def test_team_list_check_raises_one_deduped_rollover_event(seeded: SqliteD1) -> None:
    routes = window_routes([])
    routes[("PL", "teams")] = {"teams": [{"name": "Arsenal FC"}, {"name": "Promoted Town AFC"}]}
    routes[("CL", "teams")] = {"teams": [{"name": "Viking FK"}]}
    result = ingest(seeded, routes)
    check: dict[str, Any] = result.summary["team_list_check"]
    assert check["EPL"] == {"teams": 2, "unresolved": ["Promoted Town AFC"]}
    assert check["UCL"] == {"teams": 1, "unresolved": []}
    ingest(seeded, routes)
    assert seeded.scalar("SELECT COUNT(*) FROM events WHERE kind = 'canonical_update_needed'") == 1
    skipped = ingest(seeded, routes, check_team_lists=False)
    assert "team_list_check" not in skipped.summary


def test_no_secret_reaches_the_summary_or_the_database(seeded: SqliteD1) -> None:
    from tests.helpers import TOKEN

    result = ingest(seeded, {("PL", "window"): 500})
    dump = (
        repr(result.summary)
        + repr(seeded.rows("SELECT * FROM source_fetch_log"))
        + repr(seeded.rows("SELECT * FROM job_runs"))
    )
    assert TOKEN not in dump
