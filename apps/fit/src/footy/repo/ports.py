"""What the repositories need from a database client. ``D1Client`` satisfies it; tests use a
SQLite-backed double (architecture section 9.5)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from footy.repo.d1_client import Row, Statement


class Database(Protocol):
    def query(self, sql: str, params: Sequence[object] = ()) -> list[Row]: ...

    def batch(self, statements: Sequence[Statement]) -> list[list[Row]]: ...
