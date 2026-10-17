"""Telegram sender for the fit job (architecture sections 6.4 and 9.2): the weekly report today,
alerts in Stage 7.

Plain ``requests`` calls to ``sendMessage`` and ``sendPhoto``. The bot token is part of every URL,
so no exception, log line or return value ever carries a URL or a response body: failures are
reduced to a short, fixed description. 429 is waited out when ``retry_after`` is short; network
errors and 5xx are retried once; anything else is permanent.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, Protocol, cast

import requests

from footy.errors import ExitCode, FootyError

log = logging.getLogger("footy.telegram")

API_BASE = "https://api.telegram.org"
TIMEOUT_S = 20.0
MAX_RETRY_AFTER_S = 5.0
MESSAGE_LIMIT = 3900  # below Telegram's 4,096; split at line boundaries


class TelegramError(FootyError):
    """A message could not be delivered (the report itself is already stored)."""

    exit_code = ExitCode.SOURCE_OUTAGE


class Poster(Protocol):
    def post(self, url: str, **kwargs: Any) -> Any: ...


def split_text(text: str, limit: int = MESSAGE_LIMIT) -> list[str]:
    """Split at line boundaries into messages of at most ``limit`` characters; a single line
    longer than the limit is cut."""
    messages: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                messages.append(current)
                current = ""
            messages.append(line[:limit])
            line = line[limit:]
        joined = f"{current}\n{line}" if current else line
        if len(joined) > limit:
            messages.append(current)
            current = line
        else:
            current = joined
    if current or not messages:
        messages.append(current)
    return messages


class TelegramSender:
    def __init__(
        self,
        token: str,
        chat_id: str,
        *,
        session: Poster | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not token or not chat_id:
            raise ValueError("a Telegram token and chat id are required")
        self._token = token
        self._chat_id = chat_id
        self._session: Poster = session if session is not None else cast(Poster, requests.Session())
        self._sleep = sleep

    def __repr__(self) -> str:  # never show the token
        return "TelegramSender(chat_id=..., token=...)"

    def _call(self, method: str, **kwargs: Any) -> None:
        url = f"{API_BASE}/bot{self._token}/{method}"
        problem = "network error"
        for attempt in range(2):
            try:
                response = self._session.post(url, timeout=TIMEOUT_S, **kwargs)
            except requests.RequestException:
                problem = "network error"
                continue
            status = int(response.status_code)
            if status == 429:
                wait = _retry_after(response)
                problem = "rate limited"
                if wait is None or wait > MAX_RETRY_AFTER_S or attempt == 1:
                    break
                self._sleep(wait)
                continue
            if status >= 500:
                problem = f"Telegram answered HTTP {status}"
                continue
            if status >= 400:
                raise TelegramError(f"Telegram refused {method}: HTTP {status}")
            try:
                ok = response.json().get("ok") is True
            except (ValueError, AttributeError):
                ok = False
            if not ok:
                raise TelegramError(f"Telegram refused {method}: not ok")
            return
        raise TelegramError(f"could not deliver {method}: {problem}")

    def send_message(self, text: str) -> int:
        """Send ``text`` (split if long); returns the number of messages sent."""
        parts = split_text(text)
        for part in parts:
            self._call("sendMessage", json={"chat_id": self._chat_id, "text": part})
        return len(parts)

    def send_photo(self, png: bytes, caption: str | None = None) -> None:
        data = {"chat_id": self._chat_id}
        if caption:
            data["caption"] = caption[:1000]
        self._call("sendPhoto", data=data, files={"photo": ("report.png", png, "image/png")})


def _retry_after(response: Any) -> float | None:
    try:
        value = response.json()["parameters"]["retry_after"]
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    return float(value) if isinstance(value, int | float) and value >= 0 else None
