"""Alerts (architecture section 9.2).

A job that wants a human to look at something records an ``alert`` event, deduplicated per key over
24 hours (section 9.6): ``raise_alert``. ``footy alert --flush`` (the last nightly step) turns every
event that was not sent yet into one Telegram message: ``deliver.flush_alerts``, with the wording in
``catalogue``. Callers of ``raise_alert`` never talk to Telegram, so a failed send cannot fail the
job that raised the alert.
"""

from __future__ import annotations

from collections.abc import Mapping

from footy.repo.ops import OpsRepo

ALERT_LEVEL = "alert"
ALERT_SOURCE = "footy"


def raise_alert(ops: OpsRepo, at: str, key: str, kind: str, detail: Mapping[str, object]) -> bool:
    """Record one alert event; returns False when the same ``key`` already alerted within 24 h."""
    return ops.record_event(at, ALERT_LEVEL, ALERT_SOURCE, kind, detail, dedupe_key=f"alert:{key}")
