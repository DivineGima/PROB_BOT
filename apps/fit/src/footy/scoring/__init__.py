"""Scoring rules, the league-frequency baseline and calibration bins (architecture section 8.7)."""

from footy.scoring.baseline import FrequencyBaseline, Result
from footy.scoring.calibration import CalibrationBin, calibration_bins
from footy.scoring.metrics import (
    MeanScores,
    ScoredForecast,
    brier_over,
    log_loss_1x2,
    mean_scores,
    outcome_1x2,
    rps,
    rps_1x2,
    rps_totals,
    score_forecast,
    total_category,
)

__all__ = [
    "CalibrationBin",
    "FrequencyBaseline",
    "MeanScores",
    "Result",
    "ScoredForecast",
    "brier_over",
    "calibration_bins",
    "log_loss_1x2",
    "mean_scores",
    "outcome_1x2",
    "rps",
    "rps_1x2",
    "rps_totals",
    "score_forecast",
    "total_category",
]
