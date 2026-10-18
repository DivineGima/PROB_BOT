"""Send the alert events that nobody has been told about yet (architecture section 9.2).

``flush_alerts`` sends one Telegram message per ``ALERT_MAX_LINES`` alerts, one line per alert. An
event is marked delivered only after Telegram accepted the message that shows it, so a failed send
is retried by the next flush and an alert is never marked without having been shown; the 24-hour
dedupe in ``raise_alert`` keeps a persistent problem from producing a message a night.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from footy.alerts import raise_alert
from footy.alerts.catalogue import describe
from footy.config import ALERT_FLUSH_HOURS, ALERT_MAX_LINES
from footy.repo.ops import OpsRepo, PendingAlert

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
    units = _units(pending)
    messages = 0
    for start in range(0, len(units), ALERT_MAX_LINES):
        chunk = units[start : start + ALERT_MAX_LINES]
        noun = "alert" if len(chunk) == 1 else "alerts"
        text = f"ALERT: {len(chunk)} {noun}\n" + "\n".join(f"- {line}" for line, _ in chunk)
        messages += sender.send_message(text)
        ops.mark_delivered([i for _, ids in chunk for i in ids], at)
    return FlushResult(len(pending), messages)


def _units(pending: Sequence[PendingAlert]) -> list[tuple[str, list[int]]]:
    """(line, event ids) per message line. Source anomalies of one kind share a line with a count:
    a feed quirk that touches dozens of fixtures every night is one piece of news, not dozens."""
    lines: list[tuple[str, list[int]]] = []
    slot: dict[str, int] = {}  # anomaly kind -> its line
    counts: dict[str, int] = {}
    for a in pending:
        if a.kind.startswith("anomaly_"):
            if a.kind in slot:
                lines[slot[a.kind]][1].append(a.event_id)
                counts[a.kind] += 1
                continue
            slot[a.kind] = len(lines)
            counts[a.kind] = 1
        lines.append((describe(a.kind, a.detail), [a.event_id]))
    for kind, index in slot.items():
        if counts[kind] > 1:
            lines[index] = (f"{lines[index][0]} ({counts[kind]} fixtures in all)", lines[index][1])
    return lines


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
