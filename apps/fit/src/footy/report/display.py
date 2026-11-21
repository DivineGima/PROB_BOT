"""[v4] Display rules shared with the Worker (architecture 4, ADR-056 and ADR-057). Pure.

The rules live in ``packages/contracts/display.json``; ``apps/bot/src/format/display.ts`` reads the
same file, and both are pinned by ``packages/contracts/golden/strongest.json``. Display only: the
strongest call is derived on read from the stored probabilities and is never stored, so a logged
prediction stays exactly as it was.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from functools import cache
from typing import Any

from footy.config import REPO_ROOT

DISPLAY_PATH = REPO_ROOT / "packages" / "contracts" / "display.json"
OUTCOMES = ("home", "draw", "away")
# Index of each over line in the stored overs (P(over 0.5) .. P(over 5.5)).
_OVER_INDEX = {"1.5": 1, "2.5": 2, "3.5": 3}


@cache
def display() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(DISPLAY_PATH.read_text(encoding="utf-8"))
    return data


def filled_cells(p: float, cells: int | None = None) -> int:
    """floor(p * cells + 0.5), clamped: the same rule as the Worker."""
    n = int(display()["bar"]["cells"]) if cells is None else cells
    clamped = min(1.0, max(0.0, p)) if math.isfinite(p) else 0.0
    return min(n, math.floor(clamped * n + 0.5))


def tolerance() -> float:
    return float(display()["strongest_call"]["tie_tolerance"])


def favourite(p1x2: Sequence[float]) -> tuple[str, float]:
    """The most likely of home, draw and away; on a tie the earlier one."""
    best = 0
    for i in (1, 2):
        if p1x2[i] > p1x2[best] + tolerance():
            best = i
    return OUTCOMES[best], float(p1x2[best])


def favourite_band(p: float) -> str:
    """``clear`` (60%+), ``slight`` (50-60%) or ``open`` (under 50%), from the label thresholds."""
    labels = display()["favourite_labels"]
    if p >= labels[0]["min"]:
        return "clear"
    if p >= labels[1]["min"]:
        return "slight"
    return "open"


def call_probability(key: str, p1x2: Sequence[float], overs: Sequence[float]) -> float:
    if key in OUTCOMES:
        return float(p1x2[OUTCOMES.index(key)])
    side, line = key.split("_")
    over = float(overs[_OVER_INDEX[line]])
    return over if side == "over" else 1.0 - over


def strongest_call(p1x2: Sequence[float], overs: Sequence[float]) -> tuple[str, float]:
    """The single outcome the bot is most sure of among the contract's candidates (ADR-057)."""
    best: tuple[str, float] | None = None
    for key in display()["strongest_call"]["candidates"]:
        p = call_probability(key, p1x2, overs)
        if not math.isfinite(p):
            continue
        if best is None or p > best[1] + tolerance():
            best = (key, p)
    return best if best is not None else ("home", float(p1x2[0]))


def outcome_of(goals_home: int, goals_away: int) -> str:
    if goals_home > goals_away:
        return "home"
    return "draw" if goals_home == goals_away else "away"


def call_hit(key: str, goals_home: int, goals_away: int) -> bool:
    if key in OUTCOMES:
        return outcome_of(goals_home, goals_away) == key
    side, line = key.split("_")
    total = goals_home + goals_away
    return total > float(line) if side == "over" else total < float(line)


def call_label(key: str, home: str = "Home", away: str = "Away") -> str:
    """``Bayern Munich win``, ``Draw``, ``Over 1.5 goals (2+)`` or ``Under 3.5 goals (3 or
    fewer)``."""
    if key == "home":
        return f"{home} win"
    if key == "away":
        return f"{away} win"
    if key == "draw":
        return "Draw"
    side, line = key.split("_")
    goals = math.floor(float(line) + 0.5)
    return (
        f"Over {line} goals ({goals}+)"
        if side == "over"
        else f"Under {line} goals ({goals - 1} or fewer)"
    )


def short_call(key: str) -> str:
    """``Home``, ``Draw``, ``Away``, ``Over 1.5``, ``Under 3.5`` (for charts)."""
    if key in OUTCOMES:
        return key.capitalize()
    side, line = key.split("_")
    return f"{side.capitalize()} {line}"
