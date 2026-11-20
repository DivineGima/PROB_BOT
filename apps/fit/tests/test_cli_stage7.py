"""``footy healthcheck`` and ``footy alert`` through the command line (architecture section 6.7)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from footy.alerts import raise_alert
from footy.cli import build_parser, main
from footy.clock import utc_now
from footy.config import Settings
from footy.repo.ops import OpsRepo
from footy.telegram import TelegramSender
from tests.helpers import SqliteD1

D1_ENV = {"CF_ACCOUNT_ID": "acct", "D1_DATABASE_ID": "dbid", "CF_D1_TOKEN": "cf-secret-token"}
TG_ENV = {
    **D1_ENV,
    "TELEGRAM_BOT_TOKEN": "123456:TEST-token-abcdefghijklmnopqrstuvwx",
    "TELEGRAM_CHAT_ID": "1001",
}


class RecordingSession:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def post(self, url: str, **kwargs: Any) -> Any:
        self.texts.append(str(kwargs.get("json", {}).get("text", "")))

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
    db: SqliteD1 | None,
    session: RecordingSession | None = None,
) -> tuple[int, dict[str, Any]]:
    def database_factory(_settings: Settings) -> SqliteD1:
        if db is None:
            raise AssertionError("the database must not be used")
        return db

    def sender_factory(token: str, chat_id: str) -> TelegramSender:
        return TelegramSender(token, chat_id, session=session or RecordingSession())

    code = main(argv, env=env, database_factory=database_factory, sender_factory=sender_factory)
    return code, json.loads(capsys.readouterr().out)


def test_the_parser_knows_the_new_commands_and_requires_one_alert_action() -> None:
    parser = build_parser()
    assert parser.parse_args(["healthcheck"]).command == "healthcheck"
    assert parser.parse_args(["alert", "--flush"]).flush is True
    assert parser.parse_args(["alert", "--text", "x", "--key", "k"]).key == "k"
    for bad in (["alert"], ["alert", "--flush", "--text", "x"]):
        with pytest.raises(SystemExit):
            parser.parse_args(bad)


def test_healthcheck_reports_each_check_and_exits_one_when_unhealthy(
    capsys: pytest.CaptureFixture[str],
) -> None:
    db = SqliteD1()
    code, out = run(["healthcheck"], capsys, env=D1_ENV, db=db)
    assert code == 1 and out["healthy"] is False
    assert out["checks"]["active_run"]["ok"] is False
    assert db.scalar("SELECT COUNT(*) FROM events WHERE kind = 'health_check_failed'") == 2


def test_alert_flush_sends_the_pending_alerts_once(capsys: pytest.CaptureFixture[str]) -> None:
    db = SqliteD1()
    # stamped now: the flush sends only alerts from the last ALERT_FLUSH_HOURS by the real clock
    raise_alert(OpsRepo(db), utc_now(), "a", "all_models_failed", {"run_id": "R9"})
    session = RecordingSession()
    code, out = run(["alert", "--flush"], capsys, env=TG_ENV, db=db, session=session)
    assert code == 0 and out["alerts"] == 1 and out["messages"] == 1
    assert len(session.texts) == 1 and "R9" in session.texts[0]
    # a second flush has nothing to say
    code, out = run(["alert", "--flush"], capsys, env=TG_ENV, db=db, session=session)
    assert code == 0 and out["alerts"] == 0 and len(session.texts) == 1


def test_alert_text_sends_once_per_key(capsys: pytest.CaptureFixture[str]) -> None:
    db = SqliteD1()
    session = RecordingSession()
    argv = ["alert", "--text", "nightly failed", "--key", "nightly:today"]
    code, out = run(argv, capsys, env=TG_ENV, db=db, session=session)
    assert code == 0 and out["sent"] is True
    code, out = run(argv, capsys, env=TG_ENV, db=db, session=session)
    assert code == 0 and out["sent"] is False
    assert len(session.texts) == 1 and "nightly failed" in session.texts[0]


def test_alert_text_still_sends_when_the_database_settings_are_missing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    session = RecordingSession()
    env = {k: v for k, v in TG_ENV.items() if k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}

    # the real database factory refuses without its settings; the alert must go out anyway
    code = main(
        ["alert", "--text", "the database is unreachable"],
        env=env,
        sender_factory=lambda t, c: TelegramSender(t, c, session=session),
    )
    capsys.readouterr()
    assert code == 0 and session.texts == ["ALERT: the database is unreachable"]


def test_alert_without_the_telegram_settings_is_a_clear_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out = run(["alert", "--flush"], capsys, env=D1_ENV, db=None)
    assert code == 2 and "TELEGRAM_BOT_TOKEN" in out["error"]
    assert "cf-secret-token" not in json.dumps(out)
