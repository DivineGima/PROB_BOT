"""Alert stub (architecture section 9.2). Full alerting is Stage 7.

Stage 4 only needs a place to say "a human should look at this": an ``alert`` event, deduplicated
per key over 24 hours (section 9.6). Stage 7 adds the Telegram sender that reads these events and
the message catalogue; callers do not change.
"""

from __future__ import annotations

from collections.abc import Mapping

from footy.repo.ops import OpsRepo

ALERT_LEVEL = "alert"
ALERT_SOURCE = "footy"


def raise_alert(ops: OpsRepo, at: str, key: str, kind: str, detail: Mapping[str, object]) -> bool:
    """Record one alert event; returns False when the same ``key`` already alerted within 24 h."""
    return ops.record_event(at, ALERT_LEVEL, ALERT_SOURCE, kind, detail, dedupe_key=f"alert:{key}")
