"""Plain data shared by the scoring job, its repository and the report (section 8.7)."""

from __future__ import annotations

from dataclasses import dataclass

SCORED = "scored"
VOID = "void"
PENDING = "pending"

# Match statuses that void a pending prediction under their own name (section 5.5).
VOIDING_STATUSES = ("POSTPONED", "CANCELLED", "SUSPENDED", "AWARDED")
UNVERIFIED_RESULT = "UNVERIFIED_RESULT"
NO_RESULT = "NO_RESULT"


@dataclass(frozen=True)
class PendingPrediction:
    """A pending prediction joined to the stored match with the same fixture identity, if any."""

    pred_id: int
    fixture_key: str
    comp_code: str
    match_date: str
    kickoff_utc: str
    p_home: float
    p_draw: float
    p_away: float
    total_json: str
    match_status: str | None
    match_goals_home: int | None
    match_goals_away: int | None
    result_basis: str | None


@dataclass(frozen=True)
class Settlement:
    """What to do with one pending prediction: score it, void it, or leave it pending."""

    pred_id: int
    action: str  # SCORED, VOID or PENDING
    void_reason: str | None = None
    goals_home: int | None = None
    goals_away: int | None = None
    rps_1x2: float | None = None
    rps_totals: float | None = None
    logloss_1x2: float | None = None
    note: str | None = None  # why a prediction stayed pending although it looked settled


@dataclass(frozen=True)
class ScoredRow:
    """The minimum the rolling ensemble weights need from a scored prediction."""

    pred_id: int
    match_date: str
    models_json: str
    goals_home: int
    goals_away: int
