"""Alert delivery (architecture section 9.2): the wording, one message per flush, delivered once,
retried after a failed send, bounded in size, and still sent when the database is the problem."""

from __future__ import annotations

import pytest

from footy.alerts import raise_alert
from footy.alerts.catalogue import MAX_LINE, describe
from footy.alerts.deliver import alert_with_text, flush_alerts
from footy.config import ALERT_FLUSH_HOURS, ALERT_MAX_LINES
from footy.repo.d1_client import D1TransientError
from footy.repo.ops import OpsRepo
from footy.telegram import TelegramError
from tests.helpers import SqliteD1

AT = "2026-10-18T01:40:00Z"


class FakeSender:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.fail = False

    def send_message(self, text: str) -> int:
        if self.fail:
            raise TelegramError("could not deliver sendMessage: network error")
        self.messages.append(text)
        return 1


@pytest.fixture
def db() -> SqliteD1:
    return SqliteD1()


def delivered(db: SqliteD1) -> list[str | None]:
    return [r["delivered_at"] for r in db.rows("SELECT delivered_at FROM events ORDER BY event_id")]


# -- the wording ------------------------------------------------------------------------------


def test_every_alert_kind_reads_as_one_plain_line() -> None:
    cases = {
        "run_rejected": {"run_id": "R1", "reasons": ["a", "b"]},
        "model_failed": {"model": "dc", "run_id": "R1", "error": "no convergence"},
        "all_models_failed": {"run_id": "R1"},
        "no_result_voided": {"count": 2, "fixtures": ["k1", "k2"]},
        "score_unreadable": {"pred_ids": [3, 4]},
        "backtest_regression": {"regressed": ["dc"], "changes": {}},
        "unmapped_team": {"name": "FC Nowhere", "matches_skipped": 2},
        "canonical_update_needed": {"competition": "EPL", "name": "Ipswich"},
        "anomaly_score_conflict": {"fd_match_id": 7},
        "health_check_failed": {"check": "run_age", "detail": "40 h old"},
        "workflow_failed": {"text": "nightly failed"},
    }
    for kind, detail in cases.items():
        line = describe(kind, detail)
        assert line and "\n" not in line and len(line) <= MAX_LINE, kind
    assert "R1" in describe("run_rejected", cases["run_rejected"])
    assert "FC Nowhere" in describe("unmapped_team", cases["unmapped_team"])
    assert describe("workflow_failed", {"text": "nightly failed"}) == "nightly failed"
    assert describe("anomaly_score_conflict", {"x": 1}).startswith("Source anomaly score_conflict")


def test_the_wording_is_bounded_and_survives_odd_details() -> None:
    long = describe("model_failed", {"model": "dc", "run_id": "R1", "error": "x" * 5000})
    assert len(long) <= MAX_LINE
    assert describe("run_rejected", {}) and describe("something_new", {"a": object()})
    many = describe("no_result_voided", {"count": 99, "fixtures": [f"k{i}" for i in range(50)]})
    assert "(+45 more)" in many
    assert "\n" not in describe("workflow_failed", {"text": "line one\nline two"})


# -- flushing ---------------------------------------------------------------------------------


def test_a_flush_sends_every_pending_alert_in_one_message_and_marks_them(db: SqliteD1) -> None:
    ops = OpsRepo(db)
    raise_alert(ops, AT, "a", "run_rejected", {"run_id": "R1", "reasons": ["bad"]})
    raise_alert(ops, AT, "b", "model_failed", {"model": "pi", "run_id": "R1", "error": "boom"})
    sender = FakeSender()

    result = flush_alerts(ops, sender, AT)

    assert (result.alerts, result.messages) == (2, 1)
    assert len(sender.messages) == 1
    text = sender.messages[0]
    assert text.startswith("ALERT: 2 alerts\n")
    assert "R1" in text and "pi" in text
    assert delivered(db) == [AT, AT]


def test_a_delivered_alert_is_never_sent_twice(db: SqliteD1) -> None:
    ops = OpsRepo(db)
    raise_alert(ops, AT, "a", "all_models_failed", {"run_id": "R1"})
    sender = FakeSender()
    flush_alerts(ops, sender, AT)
    again = flush_alerts(ops, sender, "2026-10-18T02:40:00Z")
    assert (again.alerts, again.messages) == (0, 0)
    assert len(sender.messages) == 1


def test_a_failed_send_leaves_the_alert_for_the_next_flush(db: SqliteD1) -> None:
    ops = OpsRepo(db)
    raise_alert(ops, AT, "a", "all_models_failed", {"run_id": "R1"})
    sender = FakeSender()
    sender.fail = True
    with pytest.raises(TelegramError):
        flush_alerts(ops, sender, AT)
    assert delivered(db) == [None]
    sender.fail = False
    assert flush_alerts(ops, sender, AT).alerts == 1
    assert delivered(db) == [AT]


def test_ingest_warnings_count_as_alerts_but_other_warnings_do_not(db: SqliteD1) -> None:
    ops = OpsRepo(db)
    ops.record_event(AT, "warn", "fd_org", "unmapped_team", {"name": "FC X", "matches_skipped": 1})
    ops.record_event(AT, "warn", "fd_org", "canonical_update_needed", {"name": "Y"})
    ops.record_event(AT, "warn", "fd_org", "anomaly_score_conflict", {"fd_match_id": 1})
    ops.record_event(AT, "warn", "bot", "something_quiet", {})
    ops.record_event(AT, "info", "bot", "ignored_update", {})
    sender = FakeSender()
    assert flush_alerts(ops, sender, AT).alerts == 3
    assert "something_quiet" not in sender.messages[0]


def test_alerts_older_than_the_window_are_not_replayed(db: SqliteD1) -> None:
    ops = OpsRepo(db)
    old = "2026-10-10T01:00:00Z"
    raise_alert(ops, old, "old", "all_models_failed", {"run_id": "Rold"})
    sender = FakeSender()
    assert flush_alerts(ops, sender, AT).alerts == 0
    assert ALERT_FLUSH_HOURS == 48 and sender.messages == []


def test_a_long_list_is_sent_in_messages_of_the_limit_and_none_is_dropped(db: SqliteD1) -> None:
    ops = OpsRepo(db)
    for i in range(ALERT_MAX_LINES + 7):
        raise_alert(ops, AT, f"k{i}", "all_models_failed", {"run_id": f"R{i}"})
    sender = FakeSender()
    result = flush_alerts(ops, sender, AT)
    assert (result.alerts, result.messages) == (ALERT_MAX_LINES + 7, 2)
    assert len(sender.messages[0].splitlines()) == 1 + ALERT_MAX_LINES
    assert len(sender.messages[1].splitlines()) == 1 + 7
    shown = "".join(sender.messages)
    assert all(f"R{i}" in shown for i in range(ALERT_MAX_LINES + 7))
    assert all(d is not None for d in delivered(db))


def test_a_failed_second_message_leaves_only_the_unshown_alerts_pending(db: SqliteD1) -> None:
    ops = OpsRepo(db)
    for i in range(ALERT_MAX_LINES + 3):
        raise_alert(ops, AT, f"k{i}", "all_models_failed", {"run_id": f"R{i}"})

    class FailsSecond(FakeSender):
        def send_message(self, text: str) -> int:
            if self.messages:
                raise TelegramError("could not deliver sendMessage: network error")
            return super().send_message(text)

    with pytest.raises(TelegramError):
        flush_alerts(ops, FailsSecond(), AT)
    assert [d is not None for d in delivered(db)] == [True] * ALERT_MAX_LINES + [False] * 3
    rest = FakeSender()
    assert flush_alerts(ops, rest, AT).alerts == 3


def test_the_same_key_alerts_once_a_day(db: SqliteD1) -> None:
    ops = OpsRepo(db)
    assert raise_alert(ops, AT, "same", "all_models_failed", {"run_id": "R1"})
    assert not raise_alert(ops, "2026-10-18T20:00:00Z", "same", "all_models_failed", {})
    assert raise_alert(ops, "2026-10-19T02:00:00Z", "same", "all_models_failed", {})


def test_marking_delivered_keeps_the_first_time_and_handles_many_ids(db: SqliteD1) -> None:
    ops = OpsRepo(db)
    for i in range(200):
        ops.record_event(AT, "alert", "footy", "k", {"i": i})
    ids = [r["event_id"] for r in db.rows("SELECT event_id FROM events")]
    ops.mark_delivered(ids[:150], "2026-10-18T03:00:00Z")
    ops.mark_delivered(ids, "2026-10-18T04:00:00Z")
    stamps = {r["delivered_at"] for r in db.rows("SELECT delivered_at FROM events")}
    assert stamps == {"2026-10-18T03:00:00Z", "2026-10-18T04:00:00Z"}
    first = db.scalar("SELECT COUNT(*) FROM events WHERE delivered_at = '2026-10-18T03:00:00Z'")
    assert first == 150
    ops.mark_delivered([], AT)  # nothing to do, no error


# -- alert with a text (a failed workflow) ----------------------------------------------------


def test_a_text_alert_is_recorded_sent_once_and_deduplicated(db: SqliteD1) -> None:
    ops = OpsRepo(db)
    sender = FakeSender()
    assert alert_with_text(ops, sender, AT, "nightly:2026-10-18", "nightly failed at ingest")
    assert not alert_with_text(ops, sender, AT, "nightly:2026-10-18", "nightly failed at ingest")
    assert len(sender.messages) == 1 and "nightly failed at ingest" in sender.messages[0]
    assert delivered(db) == [AT]


def test_a_text_alert_is_sent_even_when_the_database_is_down(db: SqliteD1) -> None:
    db.fail_next = D1TransientError("database unreachable")
    sender = FakeSender()
    assert alert_with_text(OpsRepo(db), sender, AT, "k", "nightly failed: the database is down")
    assert sender.messages == ["ALERT: nightly failed: the database is down"]


def test_a_failure_while_marking_delivered_does_not_send_the_text_twice(db: SqliteD1) -> None:
    sender = FakeSender()
    db.fail_when = lambda statements: any("SET delivered_at" in s.sql for s in statements)
    with pytest.raises(D1TransientError):
        alert_with_text(OpsRepo(db), sender, AT, "k", "nightly failed")
    assert len(sender.messages) == 1  # sent once; the next flush finds it still pending
    assert delivered(db) == [None]


def test_a_text_alert_without_a_database_is_sent_directly() -> None:
    sender = FakeSender()
    assert alert_with_text(None, sender, AT, "k", "x" * 900)
    assert len(sender.messages[0]) <= len("ALERT: ") + 500
