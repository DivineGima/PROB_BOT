"""Plain-text backtest report (the "report writer" of essentials Stage 3 step 6)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def _f(value: object, digits: int = 4) -> str:
    return f"{value:.{digits}f}" if isinstance(value, int | float) else "-"


def _overall(entry: Mapping[str, object]) -> Mapping[str, object]:
    overall = entry.get("overall")
    return overall if isinstance(overall, dict) else {}


def format_report(summary: Mapping[str, object], sweep: Sequence[Mapping[str, object]] = ()) -> str:
    """Overall and per-competition RPS of every model against the baseline, then the sweep."""
    lines = [
        f"Walk-forward backtest ({summary.get('label')})",
        f"test period {summary.get('test_from')} .. {summary.get('test_to')}, "
        f"{summary.get('folds')} folds of {summary.get('fold_days')} days, "
        f"{summary.get('forecast_matches')} matches forecast, "
        f"{summary.get('skipped_insufficient_history')} skipped (insufficient history)",
        "",
    ]
    baseline = summary.get("baseline")
    models = summary.get("models")
    base_entry: Mapping[str, object] = baseline if isinstance(baseline, dict) else {}
    model_entries: Mapping[str, object] = models if isinstance(models, dict) else {}

    lines.append(f"{'':<10}{'RPS 1X2':>9}{'RPS tot':>9}{'logloss':>9}{'skill':>8}  verdict")
    base_overall = _overall(base_entry)
    lines.append(
        f"{'baseline':<10}{_f(base_overall.get('rps_1x2')):>9}"
        f"{_f(base_overall.get('rps_totals')):>9}{_f(base_overall.get('logloss_1x2')):>9}"
    )
    for name, raw in model_entries.items():
        entry: Mapping[str, object] = raw if isinstance(raw, dict) else {}
        overall = _overall(entry)
        verdict = "beats baseline" if entry.get("beats_baseline") else "does NOT beat baseline"
        lines.append(
            f"{name:<10}{_f(overall.get('rps_1x2')):>9}{_f(overall.get('rps_totals')):>9}"
            f"{_f(overall.get('logloss_1x2')):>9}{_f(entry.get('rps_skill_vs_baseline')):>8}"
            f"  {verdict} (paired diff {_f(entry.get('paired_rps_diff_mean'), 5)} "
            f"+/- {_f(entry.get('paired_rps_diff_se'), 5)})"
        )

    per_comp_base = base_entry.get("per_competition")
    if isinstance(per_comp_base, dict) and per_comp_base:
        lines += ["", "Per competition (RPS 1X2, n):"]
        header = f"{'comp':<6}{'n':>6}{'baseline':>10}" + "".join(f"{m:>10}" for m in model_entries)
        lines.append(header)
        for comp, data in per_comp_base.items():
            text = f"{comp:<6}{data.get('n', 0):>6}{_f(data.get('rps_1x2')):>10}"
            for raw in model_entries.values():
                per = raw.get("per_competition") if isinstance(raw, dict) else None
                cell = per.get(comp, {}) if isinstance(per, dict) else {}
                text += f"{_f(cell.get('rps_1x2')):>10}"
            lines.append(text)

    failures = summary.get("fold_failures")
    if isinstance(failures, dict) and any(failures.values()):
        lines += ["", f"Folds where a model failed to fit: {failures}"]
        details = summary.get("fold_failure_details")
        if isinstance(details, list):
            for d in details:
                if isinstance(d, dict):
                    lines.append(
                        f"  {d.get('model')} fold {d.get('fold_start')} "
                        f"({d.get('training_matches')} training matches): {d.get('error')}"
                    )

    if sweep:
        lines += ["", "Half-life / shrinkage sweep (mean RPS 1X2; lower is better):"]
        for entry in sweep:
            scores = "  ".join(f"{k}={_f(v)}" for k, v in entry.items() if k.startswith("rps_"))
            lines.append(
                f"  half_life={entry.get('half_life_days')!s:>6}"
                f"  shrink_team={entry.get('shrink_team')!s:>5}  {scores}"
            )
        lines.append("The sweep chooses starting values on history; it is not validation.")
    return "\n".join(lines)
