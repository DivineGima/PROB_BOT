"""Settle one pending prediction (architecture section 8.7, ADR-028). Pure.

A pending prediction is matched to the stored match with the same ``(match_date, comp_code, home,
away)``. Then:

* ``FINISHED`` with a verified 90-minute score -> scored (RPS 1X2, RPS totals, log loss);
* ``FINISHED`` with an unverified score -> void ``UNVERIFIED_RESULT``;
* ``POSTPONED``, ``CANCELLED``, ``SUSPENDED``, ``AWARDED`` -> void under that name;
* anything else (still scheduled or in play, or no matching row at all, which is what a
  rescheduled match looks like because its date changed) -> pending, until ``NO_RESULT_DAYS`` have
  passed since kickoff, then void ``NO_RESULT``.

A prediction whose stored data cannot be read (a corrupt total-goals distribution) is left pending
with a note instead of crashing the nightly job or being scored wrongly.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from footy.config import NO_RESULT_DAYS
from footy.models.grid import TOTAL_CATEGORIES
from footy.score.types import (
    NO_RESULT,
    PENDING,
    SCORED,
    UNVERIFIED_RESULT,
    VOID,
    VOIDING_STATUSES,
    PendingPrediction,
    Settlement,
)
from footy.scoring.metrics import log_loss_1x2, rps_1x2, rps_totals

VERIFIED_BASES = ("regular", "ft_90")


def parse_instant(text: str) -> datetime | None:
    """``YYYY-MM-DDTHH:MM:SSZ`` (or with an offset) as an aware UTC datetime; None if unreadable."""
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def kickoff_of(p: PendingPrediction) -> datetime:
    """The kickoff, or end of the fixture's UTC day when the stored time cannot be read."""
    moment = parse_instant(p.kickoff_utc)
    if moment is not None:
        return moment
    try:
        day = date.fromisoformat(p.match_date)
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
    return datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=UTC)


def _total_pmf(total_json: str) -> list[float] | None:
    try:
        pmf = json.loads(total_json)
    except ValueError:
        return None
    if (
        not isinstance(pmf, list)
        or len(pmf) != TOTAL_CATEGORIES
        or not all(isinstance(v, int | float) for v in pmf)
    ):
        return None
    return [float(v) for v in pmf]


def settle(p: PendingPrediction, now: datetime) -> Settlement:
    status = p.match_status
    if status == "FINISHED":
        verified = (
            p.result_basis in VERIFIED_BASES
            and p.match_goals_home is not None
            and p.match_goals_away is not None
        )
        if not verified:
            return Settlement(p.pred_id, VOID, UNVERIFIED_RESULT)
        goals_home, goals_away = int(p.match_goals_home or 0), int(p.match_goals_away or 0)
        pmf = _total_pmf(p.total_json)
        if pmf is None:
            return Settlement(
                p.pred_id, PENDING, note="the stored total-goals distribution is unreadable"
            )
        return Settlement(
            p.pred_id,
            SCORED,
            goals_home=goals_home,
            goals_away=goals_away,
            rps_1x2=rps_1x2(p.p_home, p.p_draw, p.p_away, goals_home, goals_away),
            rps_totals=rps_totals(pmf, goals_home, goals_away),
            logloss_1x2=log_loss_1x2(p.p_home, p.p_draw, p.p_away, goals_home, goals_away),
        )
    if status in VOIDING_STATUSES:
        return Settlement(p.pred_id, VOID, status)
    if now >= kickoff_of(p) + timedelta(days=NO_RESULT_DAYS):
        return Settlement(p.pred_id, VOID, NO_RESULT)
    return Settlement(p.pred_id, PENDING)
