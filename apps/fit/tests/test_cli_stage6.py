"""`footy score` and `footy report` through the command line (architecture section 6.7)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from footy.cli import build_parser, main
from footy.config import Settings, load_settings
from footy.errors import ConfigError
from footy.telegram import TelegramSender
from tests.db_seed import seed_match, seed_prediction, seed_reference
from tests.helpers import SqliteD1

D1_ENV = {"CF_ACCOUNT_ID": "acct", "D1_DATABASE_ID": "dbid", "CF_D1_TOKEN": "cf-secret-token"}
TG_ENV = {
    **D1_ENV,
    "TELEGRAM_BOT_TOKEN": "123456:TEST-token-abcdefghijklmnopqrstuvwx",
    "TELEGRAM_CHAT_ID": "1001",
}


class RecordingSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def post(self, url: str, **kwargs: Any) -> Any:
        self.calls.append(url.rsplit("/", 1)[1])

        class Reply:
            status_code = 200

            def json(self) -> dict[str, bool]:
                return {"ok": True}

        return Reply()


def run(
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
    *,
    env: dict[str, str],
    db: SqliteD1,
    session: RecordingSession | None = None,
) -> tuple[int, dict[str, Any]]:
    def database_factory(_settings: Settings) -> SqliteD1:
        return db

    def sender_factory(token: str, chat_id: str) -> TelegramSender:
        return TelegramSender(token, chat_id, session=session or RecordingSession())

    code = main(argv, env=env, database_factory=database_factory, sender_factory=sender_factory)
    out = capsys.readouterr().out
    return code, json.loads(out)


@pytest.fixture
def db() -> SqliteD1:
    d = SqliteD1()
    seed_reference(d)
    seed_prediction(d, home=1, away=2)
    seed_match(d, home=1, away=2, goals=(2, 0))
    return d


def test_score_needs_only_the_database_and_prints_a_summary(
    db: SqliteD1, capsys: pytest.CaptureFixture[str]
) -> None:
    code, summary = run(["score"], capsys, env=D1_ENV, db=db)
    assert code == 0 and summary["scored"] == 1 and summary["mode"] == "score"
    assert db.scalar("SELECT status FROM predictions") == "scored"


def test_score_without_the_database_settings_is_a_config_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["score"], env={})
    out = json.loads(capsys.readouterr().out)
    assert code == 2 and "CF_ACCOUNT_ID" in out["error"]


def test_report_without_send_needs_no_telegram_settings(
    db: SqliteD1, capsys: pytest.CaptureFixture[str]
) -> None:
    run(["score"], capsys, env=D1_ENV, db=db)
    code, summary = run(["report"], capsys, env=D1_ENV, db=db)
    assert code == 0 and summary["send"] is False and "sent" not in summary
    assert summary["n_scored"] == 1 and "Weekly report" in summary["text"]


def test_report_send_without_telegram_settings_fails_cleanly_and_names_the_variables(
    db: SqliteD1, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = run(["report", "--send"], capsys, env=D1_ENV, db=db)
    assert code == 2
    assert "TELEGRAM_BOT_TOKEN" in out["error"] and "TELEGRAM_CHAT_ID" in out["error"]
    assert db.scalar("SELECT COUNT(*) FROM calibration_snapshots") == 0


def test_report_send_delivers_through_the_sender(
    db: SqliteD1, capsys: pytest.CaptureFixture[str]
) -> None:
    run(["score"], capsys, env=TG_ENV, db=db)
    session = RecordingSession()
    code, summary = run(["report", "--send"], capsys, env=TG_ENV, db=db, session=session)
    assert code == 0 and summary["sent"] is True
    assert session.calls == ["sendMessage", "sendPhoto"]
    assert "123456:TEST" not in json.dumps(summary)


def test_report_monday_only_follows_the_real_weekday(
    db: SqliteD1, capsys: pytest.CaptureFixture[str]
) -> None:
    from datetime import UTC, datetime

    code, summary = run(["report", "--monday-only"], capsys, env=D1_ENV, db=db)
    assert code == 0
    if datetime.now(UTC).weekday() == 0:
        assert "skipped" not in summary
    else:
        assert summary["skipped"] == "not a Monday"


def test_the_backtest_regression_options_parse() -> None:
    args = build_parser().parse_args(
        ["backtest", "--fail-on-regression", "--regression-tolerance", "0.01"]
    )
    assert args.fail_on_regression is True and args.regression_tolerance == 0.01
    defaults = build_parser().parse_args(["backtest"])
    assert defaults.fail_on_regression is False and defaults.regression_tolerance == 0.003


def test_the_telegram_settings_are_read_hidden_and_checked() -> None:
    settings = load_settings(TG_ENV)
    assert settings.require_telegram() == ("123456:TEST-token-abcdefghijklmnopqrstuvwx", "1001")
    assert "TEST-token" not in repr(settings) and "1001" not in repr(settings)
    with pytest.raises(ConfigError, match="TELEGRAM_BOT_TOKEN"):
        load_settings({"TELEGRAM_CHAT_ID": "1"}).require_telegram()
    with pytest.raises(ConfigError, match="TELEGRAM_CHAT_ID"):
        load_settings({"TELEGRAM_BOT_TOKEN": "t"}).require_telegram()
