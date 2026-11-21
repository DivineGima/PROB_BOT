"""Contracts the Worker's bot commands read from Python (architecture 3, section 6.10; essentials 3
step 3): the team-name normaliser vectors and the ``metrics_json`` keys that ``/report`` shows."""

from __future__ import annotations

import json
from typing import Any

import pytest

from footy.aliases.normalise import normalise
from footy.models.golden import GOLDEN_DIR
from tests.test_report import metrics_for, report_row

VECTORS = json.loads((GOLDEN_DIR / "normalise.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", VECTORS, ids=lambda c: ascii(c["input"]))
def test_the_python_normaliser_gives_the_shared_vectors(case: dict[str, str]) -> None:
    # apps/bot/src/commands/normalise.ts is checked against the same file by Vitest.
    assert normalise(case["input"]) == case["expected"]


def test_the_vectors_cover_the_tricky_cases() -> None:
    inputs = {c["input"] for c in VECTORS}
    assert {"Bodø/Glimt", "Fenerbahçe", "1. FC Köln", "FC", ""} <= inputs
    assert len(VECTORS) >= 30


# Keys of ``metrics_json`` the Worker's /report reads (architecture 3, section 6.10). Renaming one
# breaks the Telegram command; add a new key beside the old one instead.
REPORT_TOP_KEYS = ("n_scored", "n_pending", "target", "omissions", "paired", "by_model")
REPORT_PAIRED_KEYS = (
    "n",
    "ensemble_rps_1x2",
    "baseline_rps_1x2",
    "mean_diff_rps_1x2",
    "ci_low",
    "ci_high",
    "level",
)


def test_compute_metrics_keeps_the_keys_report_reads() -> None:
    rows = [report_row(i, goals=(i % 3, 1)) for i in range(1, 41)]
    metrics: dict[str, Any] = metrics_for(rows, omissions={"DRIFT": 2})
    for key in REPORT_TOP_KEYS:
        assert key in metrics, key
    for key in REPORT_PAIRED_KEYS:
        assert key in metrics["paired"], key
    assert {"rate", "by_reason"} <= set(metrics["omissions"])
    for model in metrics["by_model"].values():
        assert {"n", "rps_1x2"} <= set(model)


def test_an_empty_report_still_has_the_counts_report_shows() -> None:
    metrics: dict[str, Any] = metrics_for([], pending=3)
    assert metrics["n_scored"] == 0
    assert metrics["n_pending"] == 3
    assert "target" in metrics
    assert "omissions" in metrics
