"""football-data.org v4 client (architecture sections 6.8 and 8.5).

* the token travels only in the ``X-Auth-Token`` header and never appears in logs, exceptions or the
  recorded resource strings;
* requests are paced (>= 6.5 s apart), retried with bounded exponential backoff on 429 / 5xx /
  network errors, and never retried on 401 / 403 / other 4xx;
* every attempt that reaches the network is recorded in ``client.fetches`` so the caller can write
  ``source_fetch_log`` (an audit trail, also for failures).
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from footy.errors import DataError, SourceAuthError, SourceOutage, SourceRestricted
from footy.ingest.pacer import Pacer

log = logging.getLogger("footy.fd_org")

API_BASE = "https://api.football-data.org/v4"
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY_S = 2.0
MAX_RETRY_AFTER_S = 70.0  # one rate-limit window is 60 s
MAX_BODY_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    retry_after: float | None = None


class Transport(Protocol):
    def get(
        self, url: str, headers: Mapping[str, str], params: Mapping[str, str], timeout: float
    ) -> HttpResponse:
        """Return the response, or raise an OSError for network failures."""
        ...


class RequestsTransport:
    """Default transport. ``requests`` is imported lazily so tests never need the network stack."""

    def __init__(self, session: Any = None) -> None:
        import requests

        self._session = session if session is not None else requests.Session()
        self._requests = requests

    def get(
        self, url: str, headers: Mapping[str, str], params: Mapping[str, str], timeout: float
    ) -> HttpResponse:
        try:
            response = self._session.get(
                url, headers=dict(headers), params=dict(params), timeout=timeout, stream=True
            )
            try:
                # iter_content turns urllib3 read errors into requests exceptions, so a connection
                # reset mid-body is retried like any other network failure.
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_content(chunk_size=65536):
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > MAX_BODY_BYTES:
                        break
                body = b"".join(chunks)
                status = response.status_code
                raw = response.headers.get("Retry-After") or response.headers.get(
                    "X-RequestCounter-Reset"
                )
            finally:
                response.close()
        except self._requests.RequestException as exc:
            # A plain OSError: the request object (which holds the token header) is not chained.
            raise OSError(type(exc).__name__) from None
        retry_after: float | None = None
        if raw is not None:
            try:
                retry_after = float(raw)
            except ValueError:
                retry_after = None
        return HttpResponse(status, body, retry_after)


@dataclass(frozen=True)
class FetchRecord:
    """One row for ``source_fetch_log``. ``resource`` never contains the token."""

    resource: str
    fetched_at: str
    http_status: int | None
    ok: bool
    content_sha256: str | None
    rows: int | None
    bytes: int | None


@dataclass(frozen=True)
class Fetched:
    resource: str
    payload: object
    record: FetchRecord


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class FdOrgClient:
    def __init__(
        self,
        token: str,
        *,
        transport: Transport | None = None,
        pacer: Pacer | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        base_delay: float = DEFAULT_BASE_DELAY_S,
        timeout: float = DEFAULT_TIMEOUT_S,
        sleep: Callable[[float], None] = time.sleep,
        rng: Callable[[], float] = random.random,
        now: Callable[[], str] = _now_iso,
    ) -> None:
        if not token:
            raise ValueError("a football-data.org token is required")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._headers = {"X-Auth-Token": token, "Accept": "application/json"}
        self._transport = transport if transport is not None else RequestsTransport()
        self._pacer = pacer if pacer is not None else Pacer(6.5)
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._timeout = timeout
        self._sleep = sleep
        self._rng = rng
        self._now = now
        self.fetches: list[FetchRecord] = []

    def __repr__(self) -> str:
        return "FdOrgClient(<token hidden>)"

    # -- public API ---------------------------------------------------------------------------

    def matches(
        self,
        fd_code: str,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        season: int | None = None,
    ) -> Fetched:
        params: dict[str, str] = {}
        if season is not None:
            params["season"] = str(season)
        if date_from is not None or date_to is not None:
            if date_from is None or date_to is None:
                raise ValueError("date_from and date_to must be given together")
            params["dateFrom"], params["dateTo"] = date_from, date_to
        return self._get(f"/competitions/{fd_code}/matches", params)

    def teams(self, fd_code: str) -> Fetched:
        return self._get(f"/competitions/{fd_code}/teams", {})

    # -- internals ----------------------------------------------------------------------------

    def _record(
        self, resource: str, status: int | None, ok: bool, body: bytes | None, rows: int | None
    ) -> FetchRecord:
        record = FetchRecord(
            resource=resource,
            fetched_at=self._now(),
            http_status=status,
            ok=ok,
            content_sha256=hashlib.sha256(body).hexdigest() if body else None,
            rows=rows,
            bytes=len(body) if body is not None else None,
        )
        self.fetches.append(record)
        return record

    def _get(self, path: str, params: Mapping[str, str]) -> Fetched:
        query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        resource = f"{path}?{query}" if query else path
        last_reason = "unknown"
        for attempt in range(1, self._max_attempts + 1):
            self._pacer.wait()
            retry_after: float | None = None
            try:
                response = self._transport.get(
                    API_BASE + path, self._headers, params, self._timeout
                )
            except OSError as exc:
                last_reason = f"network error ({type(exc).__name__})"
                self._record(resource, None, False, None, None)
            else:
                if response.status == 200:
                    return self._accept(resource, response)
                self._record(resource, response.status, False, None, None)
                if response.status == 401:
                    raise SourceAuthError("football-data.org rejected the token (HTTP 401)")
                if response.status == 403:
                    raise SourceRestricted(
                        f"football-data.org: {resource} is not available on this plan (HTTP 403)"
                    )
                if response.status == 429 or response.status >= 500:
                    last_reason = f"HTTP {response.status}"
                    retry_after = response.retry_after
                else:
                    raise DataError(
                        f"football-data.org rejected {resource} (HTTP {response.status})"
                    )

            if attempt == self._max_attempts:
                break
            delay = self._base_delay * (2 ** (attempt - 1)) * (0.5 + self._rng())
            if retry_after is not None:
                delay = max(delay, min(retry_after, MAX_RETRY_AFTER_S))
            log.warning(
                "football-data.org request failed (%s); retry %d/%d in %.1fs",
                last_reason,
                attempt,
                self._max_attempts - 1,
                delay,
            )
            self._sleep(delay)
        raise SourceOutage(
            f"football-data.org unavailable after {self._max_attempts} attempts: {last_reason}"
        )

    def _accept(self, resource: str, response: HttpResponse) -> Fetched:
        if len(response.body) > MAX_BODY_BYTES:
            self._record(resource, 200, False, None, None)
            raise DataError(f"football-data.org response for {resource} is too large")
        try:
            payload = json.loads(response.body)
        except ValueError:
            self._record(resource, 200, False, response.body, None)
            raise DataError(f"football-data.org returned non-JSON for {resource}") from None
        rows: int | None = None
        if isinstance(payload, dict):
            for key in ("matches", "teams"):
                value = payload.get(key)
                if isinstance(value, list):
                    rows = len(value)
        record = self._record(resource, 200, True, response.body, rows)
        return Fetched(resource, payload, record)
