"""League-frequency baseline (architecture section 8.7): for each competition, the H/D/A
frequencies, the over frequencies and the total-goals distribution over the training results.
This is the forecast the ensemble must beat on RPS (PRD success metric). A competition with too
few results falls back to the pooled frequencies, never to a guess."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from footy.models.grid import OVER_LINES, TOTAL_CATEGORIES, Markets
from footy.scoring.metrics import outcome_1x2, total_category

MIN_COMPETITION_MATCHES = 30
POOLED = "*"


@dataclass(frozen=True)
class Result:
    """One verified finished match: the minimum a baseline, a fit or a backtest needs."""

    comp_code: str
    goals_home: int
    goals_away: int


class _Counts:
    def __init__(self) -> None:
        self.n = 0
        self.outcomes = [0, 0, 0]
        self.overs = [0] * len(OVER_LINES)
        self.totals = [0] * TOTAL_CATEGORIES

    def add(self, goals_home: int, goals_away: int) -> None:
        self.n += 1
        self.outcomes[outcome_1x2(goals_home, goals_away)] += 1
        total = goals_home + goals_away
        for k, line in enumerate(OVER_LINES):
            if total > line:
                self.overs[k] += 1
        self.totals[total_category(goals_home, goals_away)] += 1

    def markets(self) -> Markets:
        n = self.n
        return Markets(
            p_home=self.outcomes[0] / n,
            p_draw=self.outcomes[1] / n,
            p_away=self.outcomes[2] / n,
            overs=tuple(c / n for c in self.overs),
            total_pmf=tuple(c / n for c in self.totals),
        )


class FrequencyBaseline:
    def __init__(self, per_competition: Mapping[str, Markets], pooled: Markets, n: int) -> None:
        self._per_competition = dict(per_competition)
        self._pooled = pooled
        self.n = n

    @classmethod
    def from_results(
        cls, results: Iterable[Result], *, min_matches: int = MIN_COMPETITION_MATCHES
    ) -> FrequencyBaseline:
        counts: dict[str, _Counts] = {}
        pooled = _Counts()
        for r in results:
            counts.setdefault(r.comp_code, _Counts()).add(r.goals_home, r.goals_away)
            pooled.add(r.goals_home, r.goals_away)
        if pooled.n == 0:
            raise ValueError("a baseline needs at least one result")
        per = {c: k.markets() for c, k in counts.items() if k.n >= min_matches}
        return cls(per, pooled.markets(), pooled.n)

    def forecast(self, comp_code: str) -> Markets:
        return self._per_competition.get(comp_code, self._pooled)

    def snapshot(self) -> dict[str, object]:
        """The frequencies as stored in ``model_runs.config_json`` (section 5.4)."""
        out: dict[str, object] = {POOLED: self._pooled.as_dict()}
        out.update({c: m.as_dict() for c, m in sorted(self._per_competition.items())})
        return {"n": self.n, "frequencies": out}
