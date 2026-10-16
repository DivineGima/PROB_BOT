"""D1 client tests against a fake REST layer: retry/backoff, chunking, resume (Stage 1 and 2)."""

from __future__ import annotations

import logging
import random
from collections.abc import Mapping
from pathlib import Path

import pytest

from footy.repo.d1_client import (
    MAX_BOUND_PARAMS,
    D1Client,
    D1PermanentError,
    D1QuotaError,
    D1TransientError,
    HttpResult,
    JsonFileProgress,
    MemoryProgress,
    Statement,
    execute_resumable,
    insert_statements,
)

TOKEN = "super-secret-token-value-123"


def ok_payload(*rows_per_statement: list[dict[str, object]]) -> dict[str, object]:
    return {
        "success": True,
        "errors": [],
        "messages": [],
        "result": [{"success": True, "results": rows, "meta": {}} for rows in rows_per_statement],
    }


def error_payload(message: str) -> dict[str, object]:
    return {"success": False, "errors": [{"code": 7500, "message": message}], "result": []}


class FakeTransport:
    """Scripted REST layer. Each item is an HttpResult or an exception to raise."""

    def __init__(self, script: list[HttpResult | Exception] | None = None) -> None:
        self.script = list(script or [])
        self.calls: list[dict[str, object]] = []

    def post(
        self, url: str, headers: Mapping[str, str], body: object, timeout: float
    ) -> HttpResult:
        self.calls.append({"url": url, "headers": dict(headers), "body": body})
        if not self.script:
            statements = body["batch"] if isinstance(body, dict) else []
            return HttpResult(200, ok_payload(*([[]] * len(statements))))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class Clock:
    def __init__(self) -> None:
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def make_client(
    transport: FakeTransport, clock: Clock | None = None, **kwargs: object
) -> tuple[D1Client, Clock]:
    clock = clock or Clock()
    client = D1Client(
        "acct",
        "db",
        TOKEN,
        transport=transport,
        sleep=clock.sleep,
        rng=lambda: 0.5,  # jitter factor exactly 1.0, so delays are base * 2**(attempt-1)
        **kwargs,  # type: ignore[arg-type]
    )
    return client, clock


# -- requests and results ---------------------------------------------------------------------


def test_query_sends_one_batch_request_with_bound_params_and_returns_rows() -> None:
    transport = FakeTransport([HttpResult(200, ok_payload([{"n": 1}]))])
    client, _ = make_client(transport)

    rows = client.query("SELECT ? AS n", [1])

    assert rows == [{"n": 1}]
    call = transport.calls[0]
    assert call["url"] == "https://api.cloudflare.com/client/v4/accounts/acct/d1/database/db/query"
    assert call["body"] == {"batch": [{"sql": "SELECT ? AS n", "params": [1]}]}
    assert call["headers"]["Authorization"] == f"Bearer {TOKEN}"  # type: ignore[index]


def test_batch_returns_rows_per_statement_in_order() -> None:
    transport = FakeTransport([HttpResult(200, ok_payload([{"a": 1}], [], [{"b": 2}]))])
    client, _ = make_client(transport)
    result = client.batch([Statement("S1"), Statement("S2"), Statement("S3")])
    assert result == [[{"a": 1}], [], [{"b": 2}]]


def test_empty_batch_makes_no_request() -> None:
    transport = FakeTransport()
    client, _ = make_client(transport)
    assert client.batch([]) == []
    assert transport.calls == []


# -- parameter validation ---------------------------------------------------------------------


def test_parameter_limit_is_enforced_before_any_request() -> None:
    transport = FakeTransport()
    client, _ = make_client(transport)
    client.query("SELECT 1", [0] * MAX_BOUND_PARAMS)  # exactly 100 is fine
    assert len(transport.calls) == 1
    with pytest.raises(ValueError, match="101 bound parameters"):
        client.query("SELECT 1", [0] * (MAX_BOUND_PARAMS + 1))
    assert len(transport.calls) == 1


def test_bad_parameter_values_are_rejected_and_bools_become_integers() -> None:
    transport = FakeTransport()
    client, _ = make_client(transport)
    for bad in (float("nan"), float("inf")):
        with pytest.raises(ValueError, match="NaN and infinity"):
            client.query("SELECT ?", [bad])
    with pytest.raises(TypeError, match="unsupported SQL parameter type: list"):
        client.query("SELECT ?", [[1]])
    client.query("SELECT ?, ?", [True, None])
    assert transport.calls[0]["body"]["batch"][0]["params"] == [1, None]  # type: ignore[index]


def test_client_requires_credentials() -> None:
    for args in (("", "db", "t"), ("a", "", "t"), ("a", "db", "")):
        with pytest.raises(ValueError):
            D1Client(*args, transport=FakeTransport())


# -- retry and backoff ------------------------------------------------------------------------


def test_retries_transient_http_errors_with_exponential_backoff_then_succeeds() -> None:
    transport = FakeTransport(
        [HttpResult(503, None), HttpResult(500, None), HttpResult(200, ok_payload([]))]
    )
    client, clock = make_client(transport, base_delay=0.5)
    assert client.query("SELECT 1") == []
    assert len(transport.calls) == 3
    assert clock.sleeps == [0.5, 1.0]


def test_gives_up_after_three_attempts_with_a_transient_error() -> None:
    transport = FakeTransport([HttpResult(502, None)] * 3)
    client, clock = make_client(transport)
    with pytest.raises(D1TransientError, match="after 3 attempts: HTTP 502"):
        client.query("SELECT 1")
    assert len(transport.calls) == 3
    assert len(clock.sleeps) == 2  # no sleep after the final attempt


def test_retries_network_errors() -> None:
    transport = FakeTransport([ConnectionError("boom"), HttpResult(200, ok_payload([]))])
    client, clock = make_client(transport)
    assert client.query("SELECT 1") == []
    assert len(clock.sleeps) == 1


def test_honours_retry_after_but_caps_it() -> None:
    transport = FakeTransport(
        [
            HttpResult(429, None, retry_after=5.0),
            HttpResult(429, None, retry_after=999.0),
            HttpResult(200, ok_payload([])),
        ]
    )
    client, clock = make_client(transport, base_delay=0.5)
    client.query("SELECT 1")
    assert clock.sleeps == [5.0, 30.0]


def test_retries_a_200_response_whose_error_text_is_documented_as_retryable() -> None:
    transport = FakeTransport(
        [
            HttpResult(200, error_payload("Network connection lost.")),
            HttpResult(200, ok_payload([])),
        ]
    )
    client, clock = make_client(transport)
    client.query("SELECT 1")
    assert len(clock.sleeps) == 1


def test_jitter_uses_the_injected_rng_within_the_documented_band() -> None:
    delays: list[float] = []
    for seed in range(20):
        rng = random.Random(seed).random
        transport = FakeTransport([HttpResult(500, None), HttpResult(200, ok_payload([]))])
        clock = Clock()
        D1Client(
            "a", "d", TOKEN, transport=transport, sleep=clock.sleep, rng=rng, base_delay=1.0
        ).query("SELECT 1")
        delays.extend(clock.sleeps)
    assert all(0.5 <= d < 1.5 for d in delays)
    assert len(set(delays)) > 1


# -- permanent failures -----------------------------------------------------------------------


def test_client_errors_are_not_retried_and_carry_d1s_message() -> None:
    transport = FakeTransport([HttpResult(400, error_payload("no such table: nope"))])
    client, clock = make_client(transport)
    with pytest.raises(D1PermanentError, match=r"HTTP 400\): no such table: nope"):
        client.query("SELECT * FROM nope")
    assert len(transport.calls) == 1
    assert clock.sleeps == []


def test_http_200_with_success_false_is_permanent_unless_documented_transient() -> None:
    transport = FakeTransport([HttpResult(200, error_payload("syntax error"))])
    client, _ = make_client(transport)
    with pytest.raises(D1PermanentError, match="syntax error"):
        client.query("SELEC 1")
    assert len(transport.calls) == 1


def test_daily_quota_errors_fail_fast_without_retry() -> None:
    message = (
        "Your account has exceeded D1's free tier daily row write limit. "
        "Upgrade to a paid plan or wait until tomorrow (midnight UTC) to continue."
    )
    transport = FakeTransport([HttpResult(429, error_payload(message))])
    client, clock = make_client(transport)
    with pytest.raises(D1QuotaError):
        client.query("INSERT INTO t VALUES (1)")
    assert len(transport.calls) == 1
    assert clock.sleeps == []


def test_a_response_with_the_wrong_statement_count_is_rejected() -> None:
    transport = FakeTransport([HttpResult(200, ok_payload([]))])
    client, _ = make_client(transport)
    with pytest.raises(D1PermanentError, match="statement count mismatch"):
        client.batch([Statement("A"), Statement("B")])


def test_a_failed_statement_inside_a_successful_batch_is_rejected() -> None:
    payload = ok_payload([], [])
    payload["result"][1]["success"] = False  # type: ignore[index]
    client, _ = make_client(FakeTransport([HttpResult(200, payload)]))
    with pytest.raises(D1PermanentError, match="failed statement"):
        client.batch([Statement("A"), Statement("B")])


def test_the_token_never_appears_in_repr_logs_or_exceptions(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="footy.d1")
    transport = FakeTransport([HttpResult(500, None)] * 3)
    client, _ = make_client(transport)
    assert TOKEN not in repr(client)
    with pytest.raises(D1TransientError) as failure:
        client.query("SELECT 1")
    assert TOKEN not in str(failure.value)
    assert TOKEN not in caplog.text
    assert "retry 1/2" in caplog.text

    rejected = FakeTransport([HttpResult(401, error_payload("Authentication error"))])
    client, _ = make_client(rejected)
    with pytest.raises(D1PermanentError) as denied:
        client.query("SELECT 1")
    assert TOKEN not in str(denied.value)


# -- chunking ---------------------------------------------------------------------------------


def total_params(statements: list[Statement]) -> int:
    return sum(len(s.params) for s in statements)


def test_insert_statements_splits_rows_so_no_statement_exceeds_100_parameters() -> None:
    rows = [(i, f"team {i}", i % 2) for i in range(250)]
    statements = insert_statements("teams", ["team_id", "canonical_name", "active"], rows)
    assert len(statements) == 8  # 33 rows (99 params) x 7 + 19 rows
    assert all(len(s.params) <= MAX_BOUND_PARAMS for s in statements)
    assert total_params(statements) == 250 * 3
    assert statements[0].sql.startswith(
        "INSERT OR IGNORE INTO teams (team_id, canonical_name, active) VALUES (?, ?, ?)"
    )
    assert statements[0].sql.count("(?, ?, ?)") == 33
    assert statements[-1].sql.count("(?, ?, ?)") == 19


def test_insert_statements_preserves_row_order_and_values() -> None:
    rows = [(i, f"n{i}") for i in range(120)]
    flat = [v for s in insert_statements("t", ["a", "b"], rows) for v in s.params]
    assert flat == [v for row in rows for v in row]


def test_insert_statements_never_exceed_the_limit_for_random_shapes() -> None:
    rng = random.Random(7)
    for _ in range(200):
        ncols = rng.randint(1, 100)
        nrows = rng.randint(0, 60)
        columns = [f"c{i}" for i in range(ncols)]
        rows = [tuple(rng.randint(0, 9) for _ in range(ncols)) for _ in range(nrows)]
        statements = insert_statements("t", columns, rows)
        assert all(len(s.params) <= MAX_BOUND_PARAMS for s in statements)
        assert total_params(statements) == nrows * ncols
        assert all(s.sql.count("?") == len(s.params) for s in statements)


def test_insert_statements_edge_cases() -> None:
    assert insert_statements("t", ["a"], []) == []
    with pytest.raises(ValueError, match="at least one column"):
        insert_statements("t", [], [])
    with pytest.raises(ValueError, match="cannot fit"):
        insert_statements("t", [f"c{i}" for i in range(101)], [])
    with pytest.raises(ValueError, match="row has 1 values, expected 2"):
        insert_statements("t", ["a", "b"], [(1,)])


def test_insert_statements_reject_unsafe_identifiers_and_keep_values_bound() -> None:
    for bad in ("t; DROP TABLE x", "t t", "1abc", "", 'a"b', "a-b"):
        with pytest.raises(ValueError, match="safe SQL identifier"):
            insert_statements(bad, ["a"], [(1,)])
        with pytest.raises(ValueError, match="safe SQL identifier"):
            insert_statements("t", [bad], [(1,)])
    hostile = "x'); DROP TABLE teams; --"
    (statement,) = insert_statements("teams", ["canonical_name"], [(hostile,)])
    assert hostile not in statement.sql
    assert statement.params == (hostile,)


def test_upsert_statements_update_non_key_columns() -> None:
    (statement,) = insert_statements(
        "matches",
        ["fd_match_id", "status", "goals_home"],
        [(1, "FINISHED", 2)],
        conflict="upsert",
        conflict_target=["fd_match_id"],
    )
    assert statement.sql.startswith("INSERT INTO matches")
    assert statement.sql.endswith(
        "ON CONFLICT (fd_match_id) DO UPDATE SET "
        "status = excluded.status, goals_home = excluded.goals_home"
    )
    with pytest.raises(ValueError, match="conflict_target"):
        insert_statements("matches", ["a"], [(1,)], conflict="upsert")
    with pytest.raises(ValueError, match="conflict_target"):
        insert_statements("matches", ["a"], [(1,)], conflict="upsert", conflict_target=["zzz"])
    (only_keys,) = insert_statements("t", ["a"], [(1,)], conflict="upsert", conflict_target=["a"])
    assert only_keys.sql.endswith("ON CONFLICT (a) DO NOTHING")


# -- resumable execution ----------------------------------------------------------------------


def numbered(n: int) -> list[Statement]:
    return [Statement("INSERT OR IGNORE INTO t (a) VALUES (?)", (i,)) for i in range(n)]


def test_execute_resumable_groups_statements_per_request() -> None:
    transport = FakeTransport()
    client, _ = make_client(transport)
    summary = execute_resumable(
        client, "boot", numbered(25), MemoryProgress(), statements_per_request=10
    )
    assert (summary.requests_sent, summary.requests_skipped, summary.statements_sent) == (3, 0, 25)
    assert [len(c["body"]["batch"]) for c in transport.calls] == [10, 10, 5]  # type: ignore[index]


def test_a_crash_mid_run_resumes_from_the_failed_request() -> None:
    progress = MemoryProgress()
    statements = numbered(25)
    # Request 1 succeeds, request 2 fails permanently.
    transport = FakeTransport(
        [HttpResult(200, ok_payload(*[[]] * 10)), HttpResult(400, error_payload("bad"))]
    )
    client, _ = make_client(transport)
    with pytest.raises(D1PermanentError):
        execute_resumable(client, "boot", statements, progress, statements_per_request=10)

    resumed = FakeTransport()
    client2, _ = make_client(resumed)
    summary = execute_resumable(client2, "boot", statements, progress, statements_per_request=10)
    assert (summary.requests_sent, summary.requests_skipped) == (2, 1)
    assert [len(c["body"]["batch"]) for c in resumed.calls] == [10, 5]  # type: ignore[index]


def test_a_finished_job_is_a_no_op_when_run_again() -> None:
    progress = MemoryProgress()
    client, _ = make_client(FakeTransport())
    execute_resumable(client, "boot", numbered(12), progress)
    again = FakeTransport()
    client2, _ = make_client(again)
    summary = execute_resumable(client2, "boot", numbered(12), progress)
    assert again.calls == []
    assert summary.requests_sent == 0
    assert summary.requests_skipped == 2


def test_changed_data_is_not_skipped_by_stale_progress() -> None:
    progress = MemoryProgress()
    client, _ = make_client(FakeTransport())
    execute_resumable(client, "boot", numbered(5), progress)
    changed = FakeTransport()
    client2, _ = make_client(changed)
    changed_rows = [
        Statement("INSERT OR IGNORE INTO t (a) VALUES (?)", (i + 100,)) for i in range(5)
    ]
    execute_resumable(client2, "boot", changed_rows, progress)
    assert len(changed.calls) == 1


def test_different_jobs_do_not_share_progress() -> None:
    progress = MemoryProgress()
    client, _ = make_client(FakeTransport())
    execute_resumable(client, "job-a", numbered(3), progress)
    other = FakeTransport()
    client2, _ = make_client(other)
    execute_resumable(client2, "job-b", numbered(3), progress)
    assert len(other.calls) == 1


def test_json_file_progress_survives_a_restart_and_tolerates_a_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "state" / "progress.json"
    first = JsonFileProgress(path)
    client, _ = make_client(FakeTransport())
    execute_resumable(client, "boot", numbered(15), first)
    assert path.exists()

    again = FakeTransport()
    client2, _ = make_client(again)
    summary = execute_resumable(client2, "boot", numbered(15), JsonFileProgress(path))
    assert again.calls == []
    assert summary.requests_skipped == 2

    path.write_text("{not json", encoding="utf-8")
    recovered = FakeTransport()
    client3, _ = make_client(recovered)
    execute_resumable(client3, "boot", numbered(15), JsonFileProgress(path))
    assert len(recovered.calls) == 2  # corrupt state means start over, never crash or skip


def test_execute_resumable_validates_its_arguments() -> None:
    client, _ = make_client(FakeTransport())
    with pytest.raises(ValueError):
        execute_resumable(client, "j", numbered(1), MemoryProgress(), statements_per_request=0)
