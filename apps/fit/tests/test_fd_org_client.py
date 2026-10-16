"""football-data.org client: pacing, retries, error mapping and token hygiene (Stage 2 step 4)."""

from __future__ import annotations

import json
import logging

import pytest

from footy.errors import DataError, SourceAuthError, SourceOutage, SourceRestricted
from footy.ingest.fd_org import API_BASE, FdOrgClient, HttpResponse
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
