"""football-data.org client: pacing, retries, error mapping and token hygiene (Stage 2 step 4)."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest

from footy.errors import DataError, SourceAuthError, SourceOutage, SourceRestricted
from footy.ingest.fd_org import API_BASE, FdOrgClient, HttpResponse, RequestsTransport
from footy.ingest.pacer import Pacer
from tests.helpers import TOKEN, ScriptedTransport, make_client

OK_BODY = json.dumps({"matches": [{"id": 1}, {"id": 2}]}).encode()


def test_sends_the_token_only_in_the_header_and_records_the_fetch() -> None:
    transport = ScriptedTransport(sequence=[HttpResponse(200, OK_BODY)])
    client = make_client(transport)
    fetched = client.matches("PL", date_from="2026-10-10", date_to="2026-10-20")
    call = transport.calls[0]
    assert call["url"] == f"{API_BASE}/competitions/PL/matches"
    assert call["headers"]["X-Auth-Token"] == TOKEN
    assert call["params"] == {"dateFrom": "2026-10-10", "dateTo": "2026-10-20"}
    record = fetched.record
    assert record.ok and record.http_status == 200 and record.rows == 2
    assert record.resource == "/competitions/PL/matches?dateFrom=2026-10-10&dateTo=2026-10-20"
    assert record.content_sha256 and record.bytes == len(OK_BODY)
    assert TOKEN not in repr(client) and TOKEN not in record.resource


def test_season_request_and_validation() -> None:
    transport = ScriptedTransport(sequence=[HttpResponse(200, OK_BODY)])
    client = make_client(transport)
    client.matches("PD", season=2024)
    assert transport.calls[0]["params"] == {"season": "2024"}
    with pytest.raises(ValueError, match="together"):
        client.matches("PD", date_from="2026-10-10")
    with pytest.raises(ValueError, match="token"):
        FdOrgClient("")


def test_pacing_waits_at_least_the_minimum_interval() -> None:
    now = [100.0]
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    pacer = Pacer(6.5, clock=lambda: now[0], sleep=sleep)
    assert pacer.wait() == 0.0  # the first request goes straight out
    now[0] += 2.0
    assert pacer.wait() == pytest.approx(4.5)
    now[0] += 10.0
    assert pacer.wait() == 0.0  # already past the interval
    assert slept == [pytest.approx(4.5)]
    with pytest.raises(ValueError):
        Pacer(-1)


def test_every_attempt_is_paced() -> None:
    now = [0.0]
    starts: list[float] = []

    class Clocked(ScriptedTransport):
        def get(self, url, headers, params, timeout):  # type: ignore[no-untyped-def]
            starts.append(now[0])
            return super().get(url, headers, params, timeout)

    transport = Clocked(sequence=[HttpResponse(500, b""), HttpResponse(200, OK_BODY)])
    client = FdOrgClient(
        TOKEN,
        transport=transport,
        pacer=Pacer(6.5, clock=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0] + s)),
        base_delay=0.0,
        sleep=lambda s: None,
        rng=lambda: 0.5,
    )
    client.matches("PL", season=2025)
    client.matches("PD", season=2025)
    # the failed first attempt, its retry and the next request are each one interval apart
    assert starts == [0.0, 6.5, 13.0]


def test_retries_5xx_and_network_errors_then_succeeds() -> None:
    sleeps: list[float] = []
    transport = ScriptedTransport(
        sequence=[OSError("ConnectionError"), HttpResponse(503, b""), HttpResponse(200, OK_BODY)]
    )
    client = make_client(transport, sleeps=sleeps)
    fetched = client.matches("PL", season=2025)
    assert fetched.record.ok
    assert len(transport.calls) == 3 and len(sleeps) == 2
    assert [r.http_status for r in client.fetches] == [None, 503, 200]


def test_429_honours_retry_after_but_bounded(caplog: pytest.LogCaptureFixture) -> None:
    sleeps: list[float] = []
    transport = ScriptedTransport(
        sequence=[HttpResponse(429, b"", retry_after=41.0), HttpResponse(200, OK_BODY)]
    )
    client = make_client(transport, sleeps=sleeps)
    with caplog.at_level(logging.WARNING, logger="footy.fd_org"):
        client.matches("PL", season=2025)
    assert sleeps == [41.0]
    assert TOKEN not in caplog.text

    sleeps.clear()
    huge = ScriptedTransport(
        sequence=[HttpResponse(429, b"", retry_after=9999.0), HttpResponse(200, OK_BODY)]
    )
    make_client(huge, sleeps=sleeps).matches("PL", season=2025)
    assert sleeps == [70.0]


def test_gives_up_after_bounded_attempts_with_source_outage() -> None:
    transport = ScriptedTransport(sequence=[HttpResponse(500, b"")] * 5)
    client = make_client(transport, max_attempts=3)
    with pytest.raises(SourceOutage, match="3 attempts") as info:
        client.matches("PL", season=2025)
    assert len(transport.calls) == 3
    assert TOKEN not in str(info.value)


def test_network_failure_every_time_is_an_outage() -> None:
    transport = ScriptedTransport(sequence=[OSError("Timeout")] * 3)
    with pytest.raises(SourceOutage, match="network error"):
        make_client(transport).matches("PL", season=2025)


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, SourceAuthError), (403, SourceRestricted), (400, DataError), (404, DataError)],
)
def test_client_errors_are_not_retried(status: int, error: type[Exception]) -> None:
    transport = ScriptedTransport(sequence=[HttpResponse(status, b'{"message": "no"}')])
    client = make_client(transport)
    with pytest.raises(error) as info:
        client.matches("PL", season=2023)
    assert len(transport.calls) == 1
    assert TOKEN not in str(info.value)
    assert client.fetches[-1].http_status == status and not client.fetches[-1].ok


def test_non_json_and_oversized_bodies_are_data_errors() -> None:
    client = make_client(ScriptedTransport(sequence=[HttpResponse(200, b"<html>")]))
    with pytest.raises(DataError, match="non-JSON"):
        client.matches("PL", season=2025)
    big = HttpResponse(200, b"x" * (20 * 1024 * 1024 + 1))
    with pytest.raises(DataError, match="too large"):
        make_client(ScriptedTransport(sequence=[big])).matches("PL", season=2025)


def test_teams_endpoint() -> None:
    body = json.dumps({"teams": [{"name": "Arsenal FC"}]}).encode()
    transport = ScriptedTransport(sequence=[HttpResponse(200, body)])
    fetched = make_client(transport).teams("PL")
    assert transport.calls[0]["url"].endswith("/competitions/PL/teams")
    assert fetched.record.rows == 1


# -- the real transport, with a stub session (no network) --------------------------------


class StubResponse:
    def __init__(
        self,
        status: int = 200,
        chunks: tuple[bytes, ...] = (),
        headers: dict[str, str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.status_code = status
        self.headers = headers or {}
        self._chunks = chunks
        self._error = error
        self.closed = False

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        yield from self._chunks
        if self._error is not None:
            raise self._error

    def close(self) -> None:
        self.closed = True


class StubSession:
    def __init__(
        self, response: StubResponse | None = None, error: Exception | None = None
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> StubResponse:
        self.calls.append({"url": url, **kwargs})
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def test_real_transport_joins_chunks_and_closes_the_response() -> None:
    response = StubResponse(200, (b'{"matches"', b": []}"), {"Retry-After": "12"})
    transport = RequestsTransport(StubSession(response))
    result = transport.get("https://x/y", {"X-Auth-Token": TOKEN}, {"season": "2025"}, 5.0)
    assert (result.status, result.body, result.retry_after) == (200, b'{"matches": []}', 12.0)
    assert response.closed


def test_real_transport_turns_mid_body_failures_into_retryable_oserrors() -> None:
    import requests

    response = StubResponse(200, (b"{",), error=requests.exceptions.ChunkedEncodingError(TOKEN))
    transport = RequestsTransport(StubSession(response))
    with pytest.raises(OSError, match="ChunkedEncodingError") as info:
        transport.get("https://x/y", {}, {}, 5.0)
    assert response.closed and TOKEN not in str(info.value) and info.value.__cause__ is None

    refused = RequestsTransport(StubSession(error=requests.exceptions.ConnectionError(TOKEN)))
    with pytest.raises(OSError, match="ConnectionError"):
        refused.get("https://x/y", {}, {}, 5.0)

    # and the client retries such a failure like any other network error
    client = FdOrgClient(
        TOKEN,
        transport=RequestsTransport(StubSession(response)),
        pacer=Pacer(0),
        base_delay=0.0,
        sleep=lambda s: None,
        rng=lambda: 0.5,
        max_attempts=2,
    )
    with pytest.raises(SourceOutage):
        client.matches("PL", season=2025)
    assert len(client.fetches) == 2


def test_real_transport_caps_the_body_and_ignores_a_bad_retry_header() -> None:
    big = StubResponse(200, (b"x" * (21 * 1024 * 1024), b"never read"), {"Retry-After": "soon"})
    result = RequestsTransport(StubSession(big)).get("https://x/y", {}, {}, 5.0)
    assert len(result.body) == 21 * 1024 * 1024 and result.retry_after is None
    with pytest.raises(DataError, match="too large"):
        make_client(ScriptedTransport(sequence=[HttpResponse(200, result.body)])).matches(
            "PL", season=2025
        )
