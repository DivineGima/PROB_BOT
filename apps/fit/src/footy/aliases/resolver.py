"""Source spelling -> team resolution. Unknown names are returned as ``None`` and reported by the
caller; nothing is ever guessed (section 8.5)."""

from __future__ import annotations

from collections.abc import Mapping

from footy.aliases.normalise import normalise


class Resolver:
    """Resolves names for ONE source from an ``alias_norm -> team key`` table.

    The team key is whatever the caller stores: a canonical name when built from the files, a
    ``team_id`` when built from the database.
    """

    def __init__(self, source: str, table: Mapping[str, str | int]) -> None:
        self.source = source
        self._table = dict(table)

    def resolve(self, name: object) -> str | int | None:
        if not isinstance(name, str):
            return None
        key = normalise(name)
        if not key:
            return None
        return self._table.get(key)

    def __len__(self) -> int:
        return len(self._table)
