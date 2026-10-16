"""D1 REST client: the ONLY place in the Python package that issues SQL.

Architecture sections 6.8, 6.9, 9.4 and 12:

* bound parameters only, at most ``MAX_BOUND_PARAMS`` (100) per statement (S10, ADR-031);
* retries with exponential backoff and jitter, at most 3 attempts, no unbounded loops;
* bulk writes go through ``insert_statements`` in chunked multi-row statements and are resumable
  per request via a ``Progress`` store.

A retried write may have been applied by the first attempt when only the response was lost, so
every statement sent through ``execute_resumable`` must be idempotent (``INSERT OR IGNORE`` or an
upsert). ``insert_statements`` only builds such statements.

The API token is never logged, never put in an exception message and hidden from ``repr``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import random
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

log = logging.getLogger("footy.d1")

MAX_BOUND_PARAMS = 100
API_BASE = "https://api.cloudflare.com/client/v4"
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY_S = 0.5
MAX_RETRY_AFTER_S = 30.0
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_STATEMENTS_PER_REQUEST = 10

SqlValue = str | int | float | None
Row = dict[str, Any]

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

# D1 error messages that its own documentation says to retry.
_TRANSIENT_MARKERS = (
    "network connection lost",
    "d1 db reset because its code was updated",
    "internal error while starting up d1 db storage",
    "d1 db is overloaded",
)
# Quota errors will not clear by retrying within the job (Free plan limits reset at 00:00 UTC).
_QUOTA_MARKER = "exceeded d1's free tier daily"


class D1Error(Exception):
    """Base class. Messages never contain the API token or request bodies."""


class D1TransientError(D1Error):
    """Retries were exhausted on a transient failure (network, 429, 5xx)."""


class D1PermanentError(D1Error):
    """The request was rejected and will not succeed on retry (4xx, SQL error)."""


class D1QuotaError(D1PermanentError):
    """The Free plan's daily row read/write limit is exhausted until 00:00 UTC."""


@dataclass(frozen=True)
class Statement:
    sql: str
    params: tuple[SqlValue, ...] = ()


@dataclass(frozen=True)
class HttpResult:
    status: int
    payload: object | None
    retry_after: float | None = None


class Transport(Protocol):
    def post(
        self, url: str, headers: Mapping[str, str], body: object, timeout: float
    ) -> HttpResult:
        """Return the HTTP result, or raise OSError-like errors for network failures."""
        ...


class RequestsTransport:
    """Default transport. Imported lazily so tests never need the network stack."""

    def __init__(self) -> None:
        import requests

        self._session = requests.Session()
        self._requests = requests

    def post(
        self, url: str, headers: Mapping[str, str], body: object, timeout: float
    ) -> HttpResult:
        try:
            response = self._session.post(url, headers=dict(headers), json=body, timeout=timeout)
        except self._requests.RequestException as exc:
            # Re-raise as a plain OSError so the token-bearing request object is not chained.
            raise OSError(type(exc).__name__) from None
        try:
            payload: object | None = response.json()
        except ValueError:
            payload = None
        retry_after: float | None = None
        raw = response.headers.get("Retry-After")
        if raw is not None:
            try:
                retry_after = float(raw)
            except ValueError:
                retry_after = None
        return HttpResult(response.status_code, payload, retry_after)


def _validate_params(params: Sequence[object]) -> tuple[SqlValue, ...]:
    if len(params) > MAX_BOUND_PARAMS:
        raise ValueError(f"{len(params)} bound parameters exceed the limit of {MAX_BOUND_PARAMS}")
    checked: list[SqlValue] = []
    for value in params:
        if isinstance(value, bool):
            checked.append(int(value))
        elif isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("NaN and infinity cannot be bound as SQL parameters")
            checked.append(value)
        elif value is None or isinstance(value, str | int):
            checked.append(value)
        else:
            raise TypeError(f"unsupported SQL parameter type: {type(value).__name__}")
    return tuple(checked)


def _error_text(payload: object | None) -> str:
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list):
            parts = [str(e.get("message", "")) for e in errors if isinstance(e, dict)]
            return "; ".join(p for p in parts if p)
    return ""


class D1Client:
    def __init__(
        self,
        account_id: str,
        database_id: str,
        api_token: str,
        *,
        transport: Transport | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        base_delay: float = DEFAULT_BASE_DELAY_S,
        timeout: float = DEFAULT_TIMEOUT_S,
        sleep: Callable[[float], None] = time.sleep,
        rng: Callable[[], float] = random.random,
    ) -> None:
        if not (account_id and database_id and api_token):
            raise ValueError("account_id, database_id and api_token are all required")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._url = f"{API_BASE}/accounts/{account_id}/d1/database/{database_id}/query"
        self._headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
        self._transport = transport if transport is not None else RequestsTransport()
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._timeout = timeout
        self._sleep = sleep
        self._rng = rng

    def __repr__(self) -> str:
        return "D1Client(<credentials hidden>)"

    # -- public API ---------------------------------------------------------------------------

    def query(self, sql: str, params: Sequence[object] = ()) -> list[Row]:
        """Run one statement and return its rows."""
        statement = Statement(sql, _validate_params(params))
        return self.batch([statement])[0]

    def batch(self, statements: Sequence[Statement]) -> list[list[Row]]:
        """Send several statements in ONE request; returns one row list per statement."""
        if not statements:
            return []
        body = {
            "batch": [
                {"sql": s.sql, "params": list(_validate_params(s.params))} for s in statements
            ]
        }
        payload = self._post_with_retry(body)
        return self._rows_per_statement(payload, len(statements))

    # -- internals ----------------------------------------------------------------------------

    @staticmethod
    def _rows_per_statement(payload: object, expected: int) -> list[list[Row]]:
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, list) or len(result) != expected:
            raise D1PermanentError("unexpected D1 response shape (statement count mismatch)")
        rows: list[list[Row]] = []
        for item in result:
            if not isinstance(item, dict) or item.get("success") is False:
                raise D1PermanentError("D1 reported a failed statement in the batch")
            got = item.get("results", [])
            rows.append(got if isinstance(got, list) else [])
        return rows

    def _post_with_retry(self, body: object) -> object:
        last_reason = "unknown"
        for attempt in range(1, self._max_attempts + 1):
            retry_after: float | None = None
            try:
                result = self._transport.post(self._url, self._headers, body, self._timeout)
            except OSError as exc:
                last_reason = f"network error ({type(exc).__name__})"
            else:
                text = _error_text(result.payload)
                lowered = text.lower()
                if _QUOTA_MARKER in lowered:
                    raise D1QuotaError("D1 free-tier daily row limit reached; resets at 00:00 UTC")
                succeeded = (
                    result.status == 200
                    and isinstance(result.payload, dict)
                    and result.payload.get("success") is True
                )
                if succeeded:
                    return result.payload
                transient = (
                    result.status == 429
                    or result.status >= 500
                    or any(marker in lowered for marker in _TRANSIENT_MARKERS)
                )
                if not transient:
                    detail = f": {text}" if text else ""
                    raise D1PermanentError(
                        f"D1 rejected the request (HTTP {result.status}){detail}"
                    )
                last_reason = f"HTTP {result.status}"
                retry_after = result.retry_after

            if attempt == self._max_attempts:
                break
            delay = self._base_delay * (2 ** (attempt - 1)) * (0.5 + self._rng())
            if retry_after is not None:
                delay = max(delay, min(retry_after, MAX_RETRY_AFTER_S))
            log.warning(
                "D1 request failed (%s); retry %d/%d in %.2fs",
                last_reason,
                attempt,
                self._max_attempts - 1,
                delay,
            )
            self._sleep(delay)
        raise D1TransientError(f"D1 unavailable after {self._max_attempts} attempts: {last_reason}")


# -- chunked, resumable bulk writes (ADR-031) --------------------------------------------------


def _check_identifier(name: str) -> str:
    if not _IDENTIFIER.match(name):
        raise ValueError(f"not a safe SQL identifier: {name!r}")
    return name


def insert_statements(
    table: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[object]],
    *,
    conflict: Literal["ignore", "upsert"] = "ignore",
    conflict_target: Sequence[str] = (),
    max_params: int = MAX_BOUND_PARAMS,
) -> list[Statement]:
    """Build multi-row, idempotent INSERT statements with at most ``max_params`` parameters each.

    Identifiers (table, columns) must be plain names and come from code, never from data; all row
    values are bound parameters. ``conflict="ignore"`` gives ``INSERT OR IGNORE``; ``"upsert"``
    needs ``conflict_target`` and updates every non-target column from the new row.
    """
    table = _check_identifier(table)
    cols = [_check_identifier(c) for c in columns]
    if not cols:
        raise ValueError("at least one column is required")
    if len(cols) > max_params:
        raise ValueError(f"{len(cols)} columns cannot fit in {max_params} bound parameters")
    suffix = ""
    verb = "INSERT OR IGNORE"
    if conflict == "upsert":
        target = [_check_identifier(c) for c in conflict_target]
        if not target or not set(target) <= set(cols):
            raise ValueError("upsert needs a conflict_target made of inserted columns")
        updates = [c for c in cols if c not in target]
        verb = "INSERT"
        set_clause = ", ".join(f"{c} = excluded.{c}" for c in updates) if updates else ""
        suffix = (
            f" ON CONFLICT ({', '.join(target)}) DO UPDATE SET {set_clause}"
            if updates
            else f" ON CONFLICT ({', '.join(target)}) DO NOTHING"
        )

    per_chunk = max_params // len(cols)
    one_row = "(" + ", ".join("?" for _ in cols) + ")"
    head = f"{verb} INTO {table} ({', '.join(cols)}) VALUES "

    statements: list[Statement] = []
    pending: list[SqlValue] = []
    count = 0

    def flush() -> None:
        nonlocal pending, count
        if count:
            sql = head + ", ".join([one_row] * count) + suffix
            statements.append(Statement(sql, tuple(pending)))
            pending, count = [], 0

    for row in rows:
        if len(row) != len(cols):
            raise ValueError(f"row has {len(row)} values, expected {len(cols)}")
        pending.extend(_validate_params(row))
        count += 1
        if count == per_chunk:
            flush()
    flush()
    return statements


class Progress(Protocol):
    def is_done(self, key: str) -> bool: ...

    def mark_done(self, key: str) -> None: ...


class MemoryProgress:
    def __init__(self) -> None:
        self._done: set[str] = set()

    def is_done(self, key: str) -> bool:
        return key in self._done

    def mark_done(self, key: str) -> None:
        self._done.add(key)


class JsonFileProgress:
    """Progress kept in a small local JSON file (never committed; see .gitignore)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._done: set[str] = set()
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                loaded = []
            if isinstance(loaded, list):
                self._done = {str(item) for item in loaded}

    def is_done(self, key: str) -> bool:
        return key in self._done

    def mark_done(self, key: str) -> None:
        self._done.add(key)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(sorted(self._done)), encoding="utf-8")
        tmp.replace(self._path)


def _step_key(job: str, index: int, group: Sequence[Statement]) -> str:
    digest = hashlib.sha256()
    for statement in group:
        digest.update(statement.sql.encode())
        digest.update(json.dumps(statement.params, separators=(",", ":")).encode())
    return f"{job}:{index}:{digest.hexdigest()[:16]}"


@dataclass(frozen=True)
class RunSummary:
    requests_sent: int
    requests_skipped: int
    statements_sent: int


def execute_resumable(
    client: D1Client,
    job: str,
    statements: Sequence[Statement],
    progress: Progress,
    *,
    statements_per_request: int = DEFAULT_STATEMENTS_PER_REQUEST,
) -> RunSummary:
    """Send statements in groups of ``statements_per_request`` per REST request.

    A group already recorded in ``progress`` is skipped, so a crashed run resumes where it
    stopped. The key includes a digest of the group, so changed data is never skipped by mistake.
    A failure raises; groups completed before it stay recorded.
    """
    if statements_per_request < 1:
        raise ValueError("statements_per_request must be at least 1")
    sent = skipped = statements_sent = 0
    for index, start in enumerate(range(0, len(statements), statements_per_request)):
        group = statements[start : start + statements_per_request]
        key = _step_key(job, index, group)
        if progress.is_done(key):
            skipped += 1
            continue
        client.batch(group)
        progress.mark_done(key)
        sent += 1
        statements_sent += len(group)
    return RunSummary(sent, skipped, statements_sent)
