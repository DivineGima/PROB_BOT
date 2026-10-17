"""The fit job's Telegram sender (architecture sections 6.4 and 9.2)."""

from __future__ import annotations

from typing import Any

import pytest
import requests

from footy.errors import ExitCode
from footy.telegram import TelegramError, TelegramSender, split_text

TOKEN = "123456:TEST-token-abcdefghijklmnopqrstuvwx"


class Reply:
    def __init__(self, status: int, body: Any = None) -> None:
        self.status_code = status
        self._body = {"ok": status == 200} if body is None else body

    def json(self) -> Any:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class Session:
    def __init__(self, *replies: Reply | Exception) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def post(self, url: str, **kwargs: Any) -> Reply:
        self.calls.append((url, kwargs))
        item = self.replies.pop(0) if self.replies else Reply(200)
        if isinstance(item, Exception):
            raise item
        return item


def sender(session: Session, sleeps: list[float] | None = None) -> TelegramSender:
    log: list[float] = [] if sleeps is None else sleeps
    return TelegramSender(TOKEN, "1001", session=session, sleep=log.append)


def test_a_message_is_posted_as_plain_text_to_the_chat() -> None:
    session = Session()
    assert sender(session).send_message("hello") == 1
    url, kwargs = session.calls[0]
    assert url == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert kwargs["json"] == {"chat_id": "1001", "text": "hello"} and kwargs["timeout"] == 20.0


def test_a_long_text_is_split_at_line_boundaries() -> None:
    text = "\n".join(f"line {i:03d} " + "x" * 90 for i in range(200))
    session = Session()
    assert sender(session).send_message(text) == len(session.calls) > 1
    for _url, kwargs in session.calls:
        assert len(kwargs["json"]["text"]) <= 3900
    rejoined = "\n".join(k["json"]["text"] for _u, k in session.calls)
    assert rejoined == text


def test_split_text_edge_cases() -> None:
    assert split_text("") == [""]
    assert split_text("a\nb", limit=10) == ["a\nb"]
    assert split_text("x" * 25, limit=10) == ["x" * 10, "x" * 10, "x" * 5]
    assert split_text("aaaa\nbbbb", limit=5) == ["aaaa", "bbbb"]


def test_a_photo_is_uploaded_as_multipart_with_a_short_caption() -> None:
    session = Session()
    sender(session).send_photo(b"\x89PNG-bytes", caption="c" * 2000)
    url, kwargs = session.calls[0]
    assert url.endswith("/sendPhoto")
    assert kwargs["data"]["chat_id"] == "1001" and len(kwargs["data"]["caption"]) == 1000
    assert kwargs["files"]["photo"] == ("report.png", b"\x89PNG-bytes", "image/png")


def test_a_short_429_is_waited_out_once() -> None:
    sleeps: list[float] = []
    session = Session(Reply(429, {"parameters": {"retry_after": 2}}), Reply(200))
    sender(session, sleeps).send_message("x")
    assert sleeps == [2] and len(session.calls) == 2


def test_a_long_or_repeated_429_fails() -> None:
    sleeps: list[float] = []
    with pytest.raises(TelegramError, match="rate limited"):
        sender(Session(Reply(429, {"parameters": {"retry_after": 99}})), sleeps).send_message("x")
    assert sleeps == []
    again = Session(
        Reply(429, {"parameters": {"retry_after": 1}}),
        Reply(429, {"parameters": {"retry_after": 1}}),
    )
    with pytest.raises(TelegramError, match="rate limited"):
        sender(again, sleeps).send_message("x")
    assert sleeps == [1]
    with pytest.raises(TelegramError):
        sender(Session(Reply(429, ValueError("no json")))).send_message("x")


def test_network_errors_and_5xx_are_retried_once() -> None:
    session = Session(requests.ConnectionError("boom"), Reply(200))
    sender(session).send_message("x")
    assert len(session.calls) == 2
    with pytest.raises(TelegramError, match="HTTP 502"):
        sender(Session(Reply(502), Reply(502))).send_message("x")
    with pytest.raises(TelegramError, match="network error"):
        sender(Session(requests.Timeout("t"), requests.Timeout("t"))).send_message("x")


def test_a_4xx_is_permanent_and_not_retried() -> None:
    session = Session(Reply(400, {"ok": False, "description": "chat not found"}))
    with pytest.raises(TelegramError, match="HTTP 400"):
        sender(session).send_message("x")
    assert len(session.calls) == 1


def test_an_ok_false_or_unreadable_answer_is_a_failure() -> None:
    with pytest.raises(TelegramError, match="not ok"):
        sender(Session(Reply(200, {"ok": False}))).send_message("x")
    with pytest.raises(TelegramError, match="not ok"):
        sender(Session(Reply(200, ValueError("html")))).send_message("x")


def test_the_token_never_appears_in_errors_or_repr() -> None:
    leaky = requests.ConnectionError(f"HTTPSConnectionPool: /bot{TOKEN}/sendMessage failed")
    with pytest.raises(TelegramError) as caught:
        sender(Session(leaky, leaky)).send_message("x")
    assert TOKEN not in str(caught.value) and "bot123456" not in str(caught.value)
    assert TOKEN not in repr(sender(Session()))
    assert caught.value.exit_code == ExitCode.SOURCE_OUTAGE


def test_a_token_and_chat_id_are_required() -> None:
    with pytest.raises(ValueError, match="required"):
        TelegramSender("", "1")
    with pytest.raises(ValueError, match="required"):
        TelegramSender("t", "")
