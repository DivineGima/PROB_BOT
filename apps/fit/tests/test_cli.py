"""The ``footy`` command: legal gate, exit codes and output hygiene (Stage 2, section 6.7)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from footy.cli import main
from footy.config import Settings, load_settings
from footy.errors import ConfigError
from footy.ingest.fd_org import FdOrgClient
from footy.repo.d1_client import D1TransientError
from tests.helpers import TOKEN, ScriptedTransport, SqliteD1, fd_match, make_client

TODAY = date(2026, 10, 17)
GOOD_ENV = {
    "FD_ORG_TOKEN": TOKEN,
    "SOURCE_ENABLED_FDORG": "1",
    "CF_ACCOUNT_ID": "acct",
    "D1_DATABASE_ID": "dbid",
    "CF_D1_TOKEN": "cf-secret-token",
}


def run(
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
    *,
    env: dict[str, str] | None = None,
    transport: ScriptedTransport | None = None,
    db: SqliteD1 | None = None,
) -> tuple[int, str]:
    shared = transport if transport is not None else ScriptedTransport({})

    def client_factory(token: str) -> FdOrgClient:
        assert token == TOKEN
        return make_client(shared)

    def database_factory(_settings: Settings) -> SqliteD1:
        if db is None:
            raise AssertionError("no database expected for this command")
        return db

    code = main(
        argv,
        env=GOOD_ENV if env is None else env,
        client_factory=client_factory,
        database_factory=database_factory,
        today=TODAY,
    )
    return code, capsys.readouterr().out


def test_the_legal_gate_blocks_everything_until_the_flag_is_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out = run(["ingest"], capsys, env={**GOOD_ENV, "SOURCE_ENABLED_FDORG": "0"})
    assert code == 2 and "SOURCE_ENABLED_FDORG" in json.loads(out)["error"]
    code, out = run(
        ["bootstrap", "--dry-run"],
        capsys,
        env={k: v for k, v in GOOD_ENV.items() if k != "SOURCE_ENABLED_FDORG"},
    )
    assert code == 2
    code, out = run(["ingest"], capsys, env={**GOOD_ENV, "FD_ORG_TOKEN": ""})
    assert code == 2 and "FD_ORG_TOKEN" in json.loads(out)["error"]


def test_dry_run_needs_no_database_and_prints_only_the_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    transport = ScriptedTransport(
        {
            ("PL", "season:2026"): {
                "matches": [fd_match(1, "Arsenal FC", "Chelsea FC", season_start="2026-08-15")]
            }
        }
    )
    env = {k: v for k, v in GOOD_ENV.items() if not k.startswith(("CF_", "D1_"))}
    code, out = run(
        ["bootstrap", "--dry-run", "--seasons", "1"], capsys, env=env, transport=transport
    )
    assert code == 0
    summary = json.loads(out)
    assert summary["mode"] == "dry-run" and summary["history_available_seasons"] == ["2026-27"]
    assert TOKEN not in out and "cf-secret-token" not in out


def test_bootstrap_then_ingest_through_the_cli(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    db = SqliteD1()
    progress = tmp_path / "p.json"
    transport = ScriptedTransport(
        {
            ("PL", "season:2026"): {
                "matches": [
                    fd_match(
                        1,
                        "Arsenal FC",
                        "Chelsea FC",
                        "2026-09-12T14:00:00Z",
                        season_start="2026-08-15",
                    )
                ]
            }
        }
    )
    code, out = run(
        ["bootstrap", "--seasons", "1", "--progress-file", str(progress)],
        capsys,
        transport=transport,
        db=db,
    )
    assert code == 0 and json.loads(out)["matches_inserted"] == 1
    assert progress.exists()
    window = ScriptedTransport(
        {
            ("PL", "window"): {
                "matches": [
                    fd_match(
                        2,
                        "Liverpool FC",
                        "Manchester City FC",
                        "2026-10-12T14:00:00Z",
                        season_start="2026-08-15",
                    )
                ]
            }
        }
    )
    code, out = run(["ingest", "--skip-team-check"], capsys, transport=window, db=db)
    assert code == 0 and json.loads(out)["matches_inserted"] == 1
    assert db.scalar("SELECT COUNT(*) FROM matches") == 2


@pytest.mark.parametrize("seasons", ["0", "11", "-1"])
def test_seasons_argument_is_validated(seasons: str, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(["bootstrap", "--dry-run", "--seasons", seasons], capsys)
    assert code == 2 and "between 1 and 10" in json.loads(out)["error"]


def test_missing_d1_settings_are_reported_without_a_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = {k: v for k, v in GOOD_ENV.items() if not k.startswith(("CF_", "D1_"))}
    code = main(
        ["ingest"],
        env=env,
        client_factory=lambda token: make_client(ScriptedTransport({})),
        today=TODAY,
    )
    out = capsys.readouterr().out
    assert code == 2 and "CF_ACCOUNT_ID" in json.loads(out)["error"]


def test_exit_codes_for_outage_and_database_failure(capsys: pytest.CaptureFixture[str]) -> None:
    db = SqliteD1()
    run(["bootstrap", "--seasons", "1", "--progress-file", "unused-progress.json"], capsys, db=db)
    Path("unused-progress.json").unlink(missing_ok=True)
    code, _ = run(
        ["ingest", "--skip-team-check"],
        capsys,
        transport=ScriptedTransport({("PL", "window"): 500}),
        db=db,
    )
    assert code == 3

    db.fail_at_request = db.requests + 1
    code, out = run(["ingest"], capsys, db=db)
    assert code == 1 and "injected failure" in json.loads(out)["error"]
    assert isinstance(D1TransientError("x"), Exception)


def test_unexpected_errors_never_print_a_traceback_or_the_token(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def boom(_token: str) -> FdOrgClient:
        raise RuntimeError(f"secret in message: {TOKEN}")

    code = main(["ingest"], env=GOOD_ENV, client_factory=boom, today=TODAY)
    out = capsys.readouterr().out
    assert (
        code == 1 and TOKEN not in out and json.loads(out) == {"error": "unexpected RuntimeError"}
    )


def test_settings_hide_secrets_and_parse_the_flag() -> None:
    settings = load_settings(GOOD_ENV)
    assert settings.source_enabled_fdorg and TOKEN not in repr(settings)
    assert "cf-secret-token" not in repr(settings)
    assert not load_settings({"SOURCE_ENABLED_FDORG": "true"}).source_enabled_fdorg
    with pytest.raises(ConfigError):
        load_settings({}).require_fd_org()
    with pytest.raises(ConfigError, match="CF_D1_TOKEN"):
        load_settings({"CF_ACCOUNT_ID": "a", "D1_DATABASE_ID": "b"}).require_d1()


def test_the_argument_parser_requires_a_command() -> None:
    with pytest.raises(SystemExit) as info:
        main([], env=GOOD_ENV)
    assert info.value.code == 2


# -- Stage 3: the backtest command ---------------------------------------------------------------


def _seeded_db() -> SqliteD1:
    from tests.db_seed import seed_world
    from tests.synthetic import generate_world

    db = SqliteD1()
    seed_world(db, generate_world(seed=21, n_leagues=3, teams_per_league=10, seasons=3))
    return db


D1_ONLY_ENV = {
    k: v for k, v in GOOD_ENV.items() if k in ("CF_ACCOUNT_ID", "D1_DATABASE_ID", "CF_D1_TOKEN")
}


def test_backtest_needs_only_the_database_not_the_football_data_gate(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    report = tmp_path / "out" / "backtest.txt"
    code, out = run(
        ["backtest", "--test-days", "90", "--fold-days", "45", "--out", str(report)],
        capsys,
        env=D1_ONLY_ENV,
        db=_seeded_db(),
    )
    assert code == 0
    summary = json.loads(out)
    assert summary["result"]["models"]["dc"]["beats_baseline"] is True
    assert "cf-secret-token" not in out
    assert "baseline" in report.read_text(encoding="utf-8")


def test_backtest_rejects_unknown_models_and_bad_numbers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out = run(["backtest", "--models", "nope"], capsys, env=D1_ONLY_ENV, db=SqliteD1())
    assert code == 2 and "unknown model" in json.loads(out)["error"]
    code, out = run(["backtest", "--half-lives", "abc"], capsys, env=D1_ONLY_ENV, db=SqliteD1())
    assert code == 2 and "--half-lives" in json.loads(out)["error"]
    code, out = run(["backtest", "--shrinks", "0"], capsys, env=D1_ONLY_ENV, db=SqliteD1())
    assert code == 2 and "positive" in json.loads(out)["error"]


def test_backtest_on_an_empty_database_exits_with_a_data_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out = run(["backtest"], capsys, env=D1_ONLY_ENV, db=SqliteD1())
    assert code == 2 and "bootstrap" in json.loads(out)["error"]


def test_backtest_without_the_database_settings_is_a_config_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["backtest"], env={})
    assert code == 2
    assert "CF_ACCOUNT_ID" in json.loads(capsys.readouterr().out)["error"]


# -- Stage 4: fit and publish ---------------------------------------------------------------------


def test_fit_then_publish_through_the_cli_and_rollback(capsys: pytest.CaptureFixture[str]) -> None:
    db = _seeded_db()
    code, out = run(["fit", "--models", "dc"], capsys, env=D1_ONLY_ENV, db=db)
    assert code == 0
    fit_summary = json.loads(out)
    assert fit_summary["models_ok"] == ["dc"] and fit_summary["run_status"] == "building"
    assert "cf-secret-token" not in out

    code, out = run(["publish"], capsys, env=D1_ONLY_ENV, db=db)
    assert code == 0 and json.loads(out)["result"] == "promoted"
    first = fit_summary["run_id"]
    assert db.rows("SELECT run_id FROM active_run")[0]["run_id"] == first

    code, out = run(["publish", "--rollback", first], capsys, env=D1_ONLY_ENV, db=db)
    assert code == 0 and json.loads(out)["result"] == "already active"


def test_fit_accepts_as_of_and_rejects_bad_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    db = _seeded_db()
    code, out = run(
        ["fit", "--models", "dc", "--as-of", "2026-01-31"], capsys, env=D1_ONLY_ENV, db=db
    )
    assert code == 0 and json.loads(out)["as_of"] == "2026-01-31"
    code, out = run(["fit", "--models", "nope"], capsys, env=D1_ONLY_ENV, db=SqliteD1())
    assert code == 2 and "unknown model" in json.loads(out)["error"]
    with pytest.raises(SystemExit):  # argparse: not a date
        run(["fit", "--as-of", "yesterday"], capsys, env=D1_ONLY_ENV, db=SqliteD1())


def test_publish_rejects_run_id_together_with_rollback(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(
        ["publish", "--run-id", "R1", "--rollback", "R2"], capsys, env=D1_ONLY_ENV, db=SqliteD1()
    )
    assert code == 2 and "either" in json.loads(out)["error"]


def test_model_commands_never_touch_football_data_org(capsys: pytest.CaptureFixture[str]) -> None:
    env = {**D1_ONLY_ENV, "SOURCE_ENABLED_FDORG": "0"}  # the legal gate is off; fit still runs
    code, _ = run(["fit", "--models", "dc"], capsys, env=env, db=_seeded_db())
    assert code == 0
