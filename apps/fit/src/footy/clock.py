"""The one UTC clock helper of the fit job (timestamps are ``YYYY-MM-DDTHH:MM:SSZ``, section 12)."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
