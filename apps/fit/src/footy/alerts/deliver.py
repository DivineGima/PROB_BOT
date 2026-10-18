"""Send the alert events that nobody has been told about yet (architecture section 9.2).

``flush_alerts`` sends one Telegram message per ``ALERT_MAX_LINES`` alerts, one line per alert. An
event is marked delivered only after Telegram accepted the message that shows it, so a failed send
is retried by the next flush and an alert is never marked without having been shown; the 24-hour
dedupe in ``raise_alert`` keeps a persistent problem from producing a message a night.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from footy.alerts import raise_alert
from footy.alerts.catalogue import describe
from footy.config import ALERT_FLUSH_HOURS, ALERT_MAX_LINES
from footy.repo.ops import OpsRepo

log = logging.getLogger("footy.alerts")


class MessageSender(Protocol):
    def send_message(self, text: str) -> int: ...


@dataclass(frozen=True)
class FlushResult:
    alerts: int  # delivered by this flush
    messages: int  # Telegram messages used


def flush_alerts(ops: OpsRepo, sender: MessageSender, at: str) -> FlushResult:
    """Send every undelivered alert from the last ``ALERT_FLUSH_HOURS``, oldest first."""
    pending = ops.pending_alerts(at, ALERT_FLUSH_HOURS)
    messages = 0
    for start in range(0, len(pending), ALERT_MAX_LINES):
        chunk = pending[start : start + ALERT_MAX_LINES]
        lines = [f"- {describe(a.kind, a.detail)}" for a in chunk]
        noun = "alert" if len(chunk) == 1 else "alerts"
        messages += sender.send_message(f"ALERT: {len(chunk)} {noun}\n" + "\n".join(lines))
        ops.mark_delivered([a.event_id for a in chunk], at)
    return FlushResult(len(pending), messages)


def alert_with_text(
    ops: OpsRepo | None, sender: MessageSender, at: str, key: str, text: str
) -> bool:
    """Send ``text`` as an alert (used when a workflow fails). Recorded with a 24-hour dedupe key
    when the database answers; when it does not (the usual reason a nightly job fails), the text is
    sent directly rather than lost. Returns False when the same key already alerted today."""
    recorded = False
    if ops is not None:
        try:
            if not raise_alert(ops, at, key, "workflow_failed", {"text": text[:500]}):
                return False
            recorded = True
        except Exception as exc:
            log.warning("alert not recorded (%s); sending it directly", type(exc).__name__)
    if recorded and ops is not None:
        # A failure here (Telegram, or marking after a successful send) leaves the alert pending for
        # the next flush; sending the text again now could deliver it twice.
        flush_alerts(ops, sender, at)
        return True
    sender.send_message(f"ALERT: {text[:500]}")
    return True
