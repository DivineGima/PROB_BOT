"""Repository for ``predictions`` and ``omissions`` on the fit side (SQL lives here only;
architecture sections 5.5 and 8.7).

The Worker creates predictions; this side only reads them and fills in the result and scoring
columns. Every update is guarded by ``status = 'pending'``, so scoring twice changes nothing, and
only the result and scoring columns are ever written (a test pins that).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from footy.repo.d1_client import MemoryProgress, Statement, execute_resumable
from footy.repo.ports import Database
from footy.score.types import SCORED, VOID, PendingPrediction, ScoredRow, Settlement

PAGE_SIZE = 500


@dataclass(frozen=True)
class ReportRow:
    """A scored prediction with everything the weekly report needs."""

    pred_id: int
    comp_code: str
    match_date: str
    run_id: str
    p_home: float
    p_draw: float
    p_away: float
    overs: tuple[float, ...]
    total_json: str
    models_json: str
    baseline_json: str
    goals_home: int
    goals_away: int
    rps_1x2: float
    rps_totals: float
    logloss_1x2: float


class PredictionsRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    # -- settling (footy score) ----------

    def pending_with_matches(self) -> list[PendingPrediction]:
        """Every pending prediction with the stored match that has its identity (if any)."""
        out: list[PendingPrediction] = []
        last_id = 0
        while True:
            rows = self._db.query(
                "SELECT p.pred_id, p.fixture_key, p.comp_code, p.match_date, p.kickoff_utc, "
                "p.p_home, p.p_draw, p.p_away, p.total_json, m.status AS m_status, "
                "m.goals_home AS m_goals_home, m.goals_away AS m_goals_away, "
                "m.result_basis AS m_basis "
                "FROM predictions p LEFT JOIN matches m ON m.match_date = p.match_date "
                "AND m.comp_code = p.comp_code AND m.home_team_id = p.home_team_id "
                "AND m.away_team_id = p.away_team_id "
                "WHERE p.status = 'pending' AND p.pred_id > ? ORDER BY p.pred_id LIMIT ?",
                (last_id, PAGE_SIZE),
            )
            for r in rows:
                out.append(
                    PendingPrediction(
                        pred_id=int(r["pred_id"]),
                        fixture_key=str(r["fixture_key"]),
                        comp_code=str(r["comp_code"]),
                        match_date=str(r["match_date"]),
                        kickoff_utc=str(r["kickoff_utc"]),
                        p_home=float(r["p_home"]),
                        p_draw=float(r["p_draw"]),
                        p_away=float(r["p_away"]),
                        total_json=str(r["total_json"]),
                        match_status=None if r["m_status"] is None else str(r["m_status"]),
                        match_goals_home=None
                        if r["m_goals_home"] is None
                        else int(r["m_goals_home"]),
                        match_goals_away=None
                        if r["m_goals_away"] is None
                        else int(r["m_goals_away"]),
                        result_basis=None if r["m_basis"] is None else str(r["m_basis"]),
                    )
                )
            if len(rows) < PAGE_SIZE:
                return out
            last_id = int(rows[-1]["pred_id"])

    def apply(self, settlements: Sequence[Settlement], at: str) -> None:
        """Write scores and voids. Idempotent: only rows still ``pending`` are touched."""
        statements: list[Statement] = []
        for s in settlements:
            if s.action == SCORED:
                statements.append(
                    Statement(
                        "UPDATE predictions SET status = 'scored', goals_home = ?, goals_away = ?, "
                        "rps_1x2 = ?, rps_totals = ?, logloss_1x2 = ?, scored_at = ? "
                        "WHERE pred_id = ? AND status = 'pending'",
                        (
                            s.goals_home,
                            s.goals_away,
                            s.rps_1x2,
                            s.rps_totals,
                            s.logloss_1x2,
                            at,
                            s.pred_id,
                        ),
                    )
                )
            elif s.action == VOID:
                statements.append(
                    Statement(
                        "UPDATE predictions SET status = 'void', void_reason = ?, scored_at = ? "
                        "WHERE pred_id = ? AND status = 'pending'",
                        (s.void_reason, at, s.pred_id),
                    )
                )
        execute_resumable(
            self._db, "score", statements, MemoryProgress(), statements_per_request=20
        )

    def counts_by_status(self) -> dict[str, int]:
        rows = self._db.query("SELECT status, COUNT(*) AS n FROM predictions GROUP BY status")
        return {str(r["status"]): int(r["n"]) for r in rows}

    # -- rolling ensemble weights (footy fit) -------------------------------------------------

    def recent_scored(self, limit: int) -> list[ScoredRow]:
        """The newest ``limit`` scored predictions, oldest first."""
        rows = self._db.query(
            "SELECT pred_id, match_date, models_json, goals_home, goals_away FROM predictions "
            "WHERE status = 'scored' ORDER BY match_date DESC, pred_id DESC LIMIT ?",
            (limit,),
        )
        out = [
            ScoredRow(
                pred_id=int(r["pred_id"]),
                match_date=str(r["match_date"]),
                models_json=str(r["models_json"]),
                goals_home=int(r["goals_home"]),
                goals_away=int(r["goals_away"]),
            )
            for r in rows
        ]
        out.reverse()
        return out

    # -- the weekly report ---------------------------------------------------------------------

    def scored_for_report(self) -> list[ReportRow]:
        out: list[ReportRow] = []
        last_id = 0
        while True:
            rows = self._db.query(
                "SELECT pred_id, comp_code, match_date, run_id, p_home, p_draw, p_away, "
                "p_over_05, p_over_15, p_over_25, p_over_35, p_over_45, p_over_55, total_json, "
                "models_json, baseline_json, goals_home, goals_away, rps_1x2, rps_totals, "
                "logloss_1x2 FROM predictions WHERE status = 'scored' AND pred_id > ? "
                "ORDER BY pred_id LIMIT ?",
                (last_id, PAGE_SIZE),
            )
            for r in rows:
                out.append(
                    ReportRow(
                        pred_id=int(r["pred_id"]),
                        comp_code=str(r["comp_code"]),
                        match_date=str(r["match_date"]),
                        run_id=str(r["run_id"]),
                        p_home=float(r["p_home"]),
                        p_draw=float(r["p_draw"]),
                        p_away=float(r["p_away"]),
                        overs=tuple(
                            float(r[f"p_over_{k}"]) for k in ("05", "15", "25", "35", "45", "55")
                        ),
                        total_json=str(r["total_json"]),
                        models_json=str(r["models_json"]),
                        baseline_json=str(r["baseline_json"]),
                        goals_home=int(r["goals_home"]),
                        goals_away=int(r["goals_away"]),
                        rps_1x2=float(r["rps_1x2"]),
                        rps_totals=float(r["rps_totals"]),
                        logloss_1x2=float(r["logloss_1x2"]),
                    )
                )
            if len(rows) < PAGE_SIZE:
                return out
            last_id = int(rows[-1]["pred_id"])

    def omission_counts(self) -> dict[str, int]:
        """Omissions by reason over every processed upload."""
        rows = self._db.query(
            "SELECT o.reason_code AS reason, COUNT(*) AS n FROM omissions o "
            "JOIN uploads u ON u.upload_id = o.upload_id WHERE u.status = 'processed' "
            "GROUP BY o.reason_code"
        )
        return {str(r["reason"]): int(r["n"]) for r in rows}

    def published_total(self) -> int:
        """Matches published across every processed upload, counted per upload like the omissions
        (so re-uploading an unchanged file raises both sides and the omission rate stays put)."""
        rows = self._db.query(
            "SELECT COALESCE(SUM(n_published), 0) AS n FROM uploads WHERE status = 'processed'"
        )
        return int(rows[0]["n"])
