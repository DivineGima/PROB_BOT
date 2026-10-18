"""The wording of every alert (architecture section 9.2). Pure.

One short line per alert, built only from the event's own detail: names of runs, models, teams and
counts. A value that is not a plain string or number is shown in a bounded form, and no line is
longer than ``MAX_LINE``, so a bad detail cannot flood the chat.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

MAX_LINE = 300
MAX_ITEMS = 5


def _text(value: object, limit: int = 120) -> str:
    if value is None:
        return "?"
    if isinstance(value, str | int | float | bool):
        text = str(value)
    else:
        try:
            text = json.dumps(value, sort_keys=True, default=str)
        except (TypeError, ValueError):
            text = "?"
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _items(value: object) -> str:
    if not isinstance(value, list | tuple) or not value:
        return _text(value)
    shown = ", ".join(_text(v, 60) for v in value[:MAX_ITEMS])
    return shown + (f" (+{len(value) - MAX_ITEMS} more)" if len(value) > MAX_ITEMS else "")


def describe(kind: str, detail: Mapping[str, object]) -> str:
    """One line for the alert event ``kind``; unknown kinds fall back to a bounded detail dump."""
    d = detail
    if kind == "run_rejected":
        line = (
            f"Model run {_text(d.get('run_id'))} was rejected by the promotion gate; the previous "
            f"run stays active. {_items(d.get('reasons'))}"
        )
    elif kind == "model_failed":
        line = (
            f"Model {_text(d.get('model'))} failed in run {_text(d.get('run_id'))}: "
            f"{_text(d.get('error'))}"
        )
    elif kind == "all_models_failed":
        line = f"Every model failed in run {_text(d.get('run_id'))}; the previous run stays active."
    elif kind == "no_result_voided":
        line = (
            f"{_text(d.get('count'))} prediction(s) were voided because no result arrived in time: "
            f"{_items(d.get('fixtures'))}"
        )
    elif kind == "score_unreadable":
        line = (
            f"Predictions could not be scored (unreadable stored data): {_items(d.get('pred_ids'))}"
        )
    elif kind == "backtest_regression":
        line = (
            f"Backtest regression: {_items(d.get('regressed'))} scored worse than in the previous "
            "backtest."
        )
    elif kind == "unmapped_team":
        line = (
            f"Unmapped team {_text(d.get('name'))}: {_text(d.get('matches_skipped'))} match(es) "
            "skipped. Add an alias."
        )
    elif kind == "canonical_update_needed":
        line = (
            f"Team {_text(d.get('name'))} ({_text(d.get('competition'))}) is in the source but "
            "not in the canonical list."
        )
    elif kind.startswith("anomaly_"):
        line = f"Source anomaly {kind.removeprefix('anomaly_')}: {_text(dict(d))}"
    elif kind == "health_check_failed":
        line = f"Health check '{_text(d.get('check'))}' failed: {_text(d.get('detail'))}"
    elif kind == "workflow_failed":
        line = _text(d.get("text"), MAX_LINE)
    else:
        line = f"{kind}: {_text(dict(d))}"
    return line if len(line) <= MAX_LINE else line[: MAX_LINE - 1] + "…"
