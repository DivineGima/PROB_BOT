"""Verify-at-build item 3 (architecture section 16): what the REAL D1 REST API does.

Run once against the real database after migration 0001 has been applied:

    CF_ACCOUNT_ID=... D1_DATABASE_ID=... CF_D1_TOKEN=... python -m footy.repo.d1_probe

It answers three questions and prints a JSON report to paste into docs/verification.md:
  1. does the REST ``batch`` form work;
  2. is the bound-parameter limit really 100 (100 accepted, 101 rejected);
  3. is a batch atomic (a failing statement rolls back the earlier writes).
It writes one marker row to ``events`` and deletes it again. It lives in ``repo/`` because it
issues SQL.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from typing import Any

from footy.repo.d1_client import D1Client, D1Error, Statement


def _placeholders(n: int) -> str:
    return ", ".join("?" for _ in range(n))


def _accepts(client: D1Client, n_params: int) -> bool:
    sql = f"SELECT {_placeholders(n_params)}"
    try:
        client.query(sql, list(range(n_params)))
    except D1Error:
        return False
    except ValueError:
        # The client itself refuses more than 100; bypass it to see what D1 does with 101.
        return _accepts_raw(client, sql, n_params)
    return True


def _accepts_raw(client: D1Client, sql: str, n_params: int) -> bool:
    body = {"batch": [{"sql": sql, "params": list(range(n_params))}]}
    try:
        client._post_with_retry(body)
    except D1Error:
        return False
    return True


def probe(client: D1Client) -> dict[str, Any]:
    report: dict[str, Any] = {}

    try:
        results = client.batch([Statement("SELECT 1 AS a"), Statement("SELECT 2 AS b")])
        report["batch_supported"] = results == [[{"a": 1}], [{"b": 2}]]
    except D1Error as exc:
        report["batch_supported"] = False
        report["batch_error"] = str(exc)

    report["params_100_accepted"] = _accepts(client, 100)
    report["params_101_accepted"] = _accepts(client, 101)

    marker = f"probe-{uuid.uuid4().hex}"
    try:
        client.batch(
            [
                Statement(
                    "INSERT INTO events (at, level, source, kind, dedupe_key) "
                    "VALUES ('1970-01-01T00:00:00Z', 'info', 'probe', 'atomicity', ?)",
                    (marker,),
                ),
                Statement("SELECT * FROM table_that_does_not_exist"),
            ]
        )
        report["atomic_batch"] = None  # the failing statement did not fail: inconclusive
    except D1Error:
        left = client.query("SELECT COUNT(*) AS n FROM events WHERE dedupe_key = ?", (marker,))
        report["atomic_batch"] = left[0]["n"] == 0
    finally:
        client.query("DELETE FROM events WHERE dedupe_key = ?", (marker,))

    return report


def main() -> int:
    try:
        client = D1Client(
            os.environ["CF_ACCOUNT_ID"], os.environ["D1_DATABASE_ID"], os.environ["CF_D1_TOKEN"]
        )
    except KeyError as missing:
        print(f"missing environment variable: {missing.args[0]}", file=sys.stderr)
        return 1
    print(json.dumps(probe(client), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
