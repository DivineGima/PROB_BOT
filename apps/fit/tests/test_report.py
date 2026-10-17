"""The weekly report: metrics, bootstrap interval, wording, chart and the job
(architecture sections 8.7 and 9.2, ADR-046)."""

from __future__ import annotations

import json
import math
from typing import Any

import pytest

from footy.errors import ExitCode
from footy.repo.predictions import PredictionsRepo, ReportRow
from footy.report.chart import render_chart
from footy.report.job import run_report_job
from footy.report.metrics import compute_metrics, largest_calibration_gap, paired_bootstrap_ci
from footy.report.text import render_text, verdict
from footy.score.job import run_score_job
from footy.scoring.metrics import rps_1x2, rps_totals
from footy.telegram import TelegramSender
from tests.db_seed import BASELINE, OVERS, TOTAL_PMF, seed_match, seed_prediction, seed_reference
from tests.helpers import SqliteD1

MODELS = json.dumps({n: {"p": [0.5, 0.3, 0.2], "total": TOTAL_PMF} for n in ("dc", "pi", "bp")})


def report_row(
    pred_id: int = 1,
    *,
    comp: str = "EPL",
    goals: tuple[int, int] = (2, 0),
    p: tuple[float, float, float] = (0.5, 0.3, 0.2),
    models: str = MODELS,
    baseline: object = BASELINE,
) -> ReportRow:
    return ReportRow(
        pred_id=pred_id,
        comp_code=comp,
        match_date=f"2026-10-{(pred_id % 28) + 1:02d}",
        run_id="R1",
        p_home=p[0],
        p_draw=p[1],
        p_away=p[2],
        overs=tuple(OVERS),
        total_json=json.dumps(TOTAL_PMF),
        models_json=models,
        baseline_json=json.dumps(baseline) if baseline is not None else "not json",
        goals_home=goals[0],
        goals_away=goals[1],
        rps_1x2=rps_1x2(p[0], p[1], p[2], goals[0], goals[1]),
        rps_totals=rps_totals(TOTAL_PMF, goals[0], goals[1]),
        logloss_1x2=-math.log(
            (p[0], p[1], p[2])[0 if goals[0] > goals[1] else 1 if goals[0] == goals[1] else 2]
        ),
    )


def metrics_for(rows: list[ReportRow], **kwargs: Any) -> dict[str, Any]:
    args: dict[str, Any] = {
        "omissions": {},
        "published_total": len(rows),
        "pending": 0,
        "n_boot": 300,
    }
    args.update(kwargs)
    return compute_metrics(rows, **args)


# -- the bootstrap interval ----------


def test_the_interval_is_deterministic_and_brackets_a_known_mean() -> None:
    values = [-0.03 + 0.01 * math.sin(i) for i in range(400)]
    first = paired_bootstrap_ci(values, n_boot=500)
    assert first == paired_bootstrap_ci(values, n_boot=500)
    assert first is not None
    low, high = first
    mean = sum(values) / len(values)
    assert low < mean < high and high - low < 0.005
    assert paired_bootstrap_ci(values, n_boot=500, seed=1) != first


def test_the_interval_widens_with_noise_and_includes_zero_for_a_null_difference() -> None:
    symmetric = [(-1) ** i * 0.05 for i in range(60)]
    low, high = paired_bootstrap_ci(symmetric, n_boot=1000) or (0.0, 0.0)
    assert low < 0 < high


def test_too_few_values_have_no_interval() -> None:
    assert paired_bootstrap_ci([0.1]) is None
    assert paired_bootstrap_ci([]) is None


# -- metrics ----------


def test_scores_baseline_and_the_paired_difference_match_hand_computation() -> None:
    rows = [report_row(1, goals=(2, 0)), report_row(2, goals=(0, 1)), report_row(3, goals=(1, 1))]
    m = metrics_for(rows)
    ens = [rows[0].rps_1x2, rows[1].rps_1x2, rows[2].rps_1x2]
    assert m["ensemble"]["rps_1x2"] == pytest.approx(sum(ens) / 3)
    base = [
        rps_1x2(0.45, 0.27, 0.28, 2, 0),
        rps_1x2(0.45, 0.27, 0.28, 0, 1),
        rps_1x2(0.45, 0.27, 0.28, 1, 1),
    ]
    assert m["paired"]["baseline_rps_1x2"] == pytest.approx(sum(base) / 3)
    assert m["paired"]["mean_diff_rps_1x2"] == pytest.approx(
        sum(e - b for e, b in zip(ens, base, strict=True)) / 3
    )
    assert m["paired"]["n"] == 3 and m["n_scored"] == 3
    assert m["progress"] == pytest.approx(3 / 300)
    # Brier of an over line against the observed totals (2, 1, 2 goals) for P(over 1.5) = 0.7
    assert m["ensemble"]["brier_overs"][1] == pytest.approx(
        ((0.7 - 1) ** 2 + (0.7 - 0) ** 2 + (0.7 - 1) ** 2) / 3
    )


def test_a_row_without_a_usable_baseline_is_scored_but_left_out_of_the_comparison() -> None:
    rows = [report_row(1), report_row(2, baseline=None), report_row(3, baseline={"p_home": 2})]
    m = metrics_for(rows)
    assert m["n_scored"] == 3 and m["paired"]["n"] == 1 and m["baseline"]["n"] == 1
    assert m["ensemble"]["rps_1x2"] == pytest.approx(rows[0].rps_1x2)


def test_per_model_and_per_competition_breakdowns() -> None:
    skipped = json.dumps({"dc": {"p": [0.4, 0.3, 0.3], "total": TOTAL_PMF}})
    rows = [report_row(1), report_row(2, comp="LL", models=skipped), report_row(3, comp="LL")]
    m = metrics_for(rows)
    assert m["by_model"]["dc"]["n"] == 3 and m["by_model"]["bp"]["n"] == 2
    assert m["by_competition"]["EPL"]["n"] == 1 and m["by_competition"]["LL"]["n"] == 2
    assert m["by_competition"]["LL"]["baseline_n"] == 2


def test_calibration_bins_hold_the_right_counts_for_outcomes_and_over_lines() -> None:
    rows = [report_row(i, goals=(2, 0) if i % 2 else (0, 0)) for i in range(1, 21)]
    m = metrics_for(rows)
    home = m["calibration"]["home"]
    assert sum(b["n"] for b in home) == 20
    assert home[0]["mean_forecast"] == pytest.approx(0.5) and home[0][
        "observed_frequency"
    ] == pytest.approx(0.5)
    assert set(m["calibration"]) == {
        "home",
        "draw",
        "away",
        "over_0.5",
        "over_1.5",
        "over_2.5",
        "over_3.5",
        "over_4.5",
        "over_5.5",
    }
    gap = largest_calibration_gap(m["calibration"]["home"], min_n=10)
    assert gap is not None and gap[0] == pytest.approx(0.5) and gap[1] == pytest.approx(0.5)
    assert largest_calibration_gap(m["calibration"]["home"], min_n=100) is None


def test_the_omission_rate_is_by_reason_over_published_plus_omitted() -> None:
    m = metrics_for([report_row(1)], omissions={"NO_FORECAST": 3, "DRIFT": 1}, published_total=12)
    assert m["omissions"] == {
        "published": 12,
        "omitted": 4,
        "rate": pytest.approx(4 / 16),
        "by_reason": {"DRIFT": 1, "NO_FORECAST": 3},
    }


def test_nothing_scored_gives_only_the_counts() -> None:
    m = metrics_for([], pending=7)
    assert m["n_scored"] == 0 and m["n_pending"] == 7 and "ensemble" not in m


# -- wording ----------


def test_the_wording_is_honest_about_small_samples() -> None:
    assert "No predictions have been scored yet" in verdict(metrics_for([]))
    few = verdict(metrics_for([report_row(i) for i in range(1, 6)]))
    assert "far too few" in few and "noise" in few


def test_the_wording_depends_on_whether_the_interval_excludes_zero() -> None:
    ahead = {"n_scored": 100, "target": 300, "paired": {"ci_low": -0.05, "ci_high": -0.01}}
    behind = {"n_scored": 100, "target": 300, "paired": {"ci_low": 0.01, "ci_high": 0.05}}
    unclear = {"n_scored": 100, "target": 300, "paired": {"ci_low": -0.02, "ci_high": 0.03}}
    assert "ahead of the baseline" in verdict(ahead) and "excludes zero" in verdict(ahead)
    assert "behind the baseline" in verdict(behind)
    assert "includes zero" in verdict(unclear) and "no difference can be claimed" in verdict(
        unclear
    )
    for m in (ahead, behind, unclear):
        assert "not a significance claim" in verdict(m)
        assert "100 of the 300" in verdict(m)


def test_reaching_the_target_is_stated() -> None:
    done = {"n_scored": 312, "target": 300, "paired": {"ci_low": -0.05, "ci_high": -0.01}}
    assert "target is reached (312 scored)" in verdict(done)


def test_the_text_has_the_numbers_a_reader_needs() -> None:
    rows = [report_row(i, goals=(2, 0) if i % 3 else (0, 1)) for i in range(1, 41)]
    text = render_text(metrics_for(rows, omissions={"NO_FORECAST": 5}, pending=4), "2026-10-19")
    assert text.startswith("Weekly report 2026-10-19")
    assert "Scored predictions: 40 of the 300 needed (13%); 4 pending." in text
    assert "95% interval" in text and "difference" in text
    assert "Models, RPS 1X2" in text and "dc " in text
    assert "By competition" in text and "EPL" in text
    assert "Calibration: the widest gap" in text
    assert "Omitted matches: 5 of 45" in text
    assert text.endswith("Probabilities, not advice.") and len(text) <= 3800


def test_the_text_for_an_empty_week_is_short_and_clear() -> None:
    text = render_text(metrics_for([], pending=3), "2026-10-19")
    assert "Scored predictions: 0 of the 300 needed (0%); 3 pending." in text
    assert "No predictions have been scored yet." in text and "Ensemble against" not in text


def test_many_competitions_are_cut_off_rather_than_overflowing() -> None:
    rows = [report_row(i, comp=f"C{i:02d}") for i in range(1, 31)]
    text = render_text(metrics_for(rows), "2026-10-19")
    assert "... and 18 more" in text and len(text) <= 3800


# -- the chart ----------


def test_the_chart_is_a_png() -> None:
    rows = [report_row(i, goals=(2, 0) if i % 2 else (1, 1)) for i in range(1, 25)]
    png = render_chart(metrics_for(rows))
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 5_000


def test_the_chart_needs_something_scored() -> None:
    with pytest.raises(ValueError, match="no scored"):
        render_chart(metrics_for([]))


# -- the job ----------


class FakeSession:
    def __init__(self, statuses: list[int] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._statuses = statuses or []

    def post(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, kwargs))
        status = self._statuses.pop(0) if self._statuses else 200

        class Response:
            status_code = status

            def json(self) -> dict[str, Any]:
                return {"ok": status == 200}

        return Response()


def sender(session: FakeSession) -> TelegramSender:
    return TelegramSender("123456:TEST-token-abcdefghijklmnopqrstuvwx", "1001", session=session)


@pytest.fixture
def scored_db() -> SqliteD1:
    db = SqliteD1()
    seed_reference(db)
    for i in range(12):
        seed_prediction(
            db,
            day=f"2026-10-{i + 1:02d}",
            home=1 + i,
            away=21 + i,
            status="scored",
            goals=(2, 0) if i % 2 else (0, 1),
            rps=(0.2, 0.1, 0.9),
        )
    seed_prediction(db, day="2026-10-20", home=30, away=31)  # still pending
    db.conn.execute(
        "INSERT INTO model_runs (run_id, status, started_at) VALUES ('R1', 'active', 't')"
    )
    db.conn.execute("INSERT INTO active_run (id, run_id, activated_at) VALUES (1, 'R1', 't')")
    return db


def clock(day: str) -> Any:
    return lambda: f"{day}T05:00:00Z"


def test_the_report_stores_a_snapshot_and_returns_the_text(scored_db: SqliteD1) -> None:
    result = run_report_job(scored_db, now=clock("2026-10-19"))
    assert result.exit_code == ExitCode.OK, result.summary
    assert result.summary["n_scored"] == 12 and "Weekly report 2026-10-19" in str(
        result.summary["text"]
    )
    snap = scored_db.rows("SELECT * FROM calibration_snapshots")
    assert len(snap) == 1
    assert (snap[0]["n_scored"], snap[0]["run_id"]) == (12, "R1")
    assert snap[0]["window_from"] == "2026-10-01" and snap[0]["window_to"] == "2026-10-12"
    stored = json.loads(snap[0]["metrics_json"])
    assert stored["n_scored"] == 12 and stored["n_pending"] == 1 and "calibration" in stored


def test_two_reports_make_two_snapshots(scored_db: SqliteD1) -> None:
    run_report_job(scored_db, now=clock("2026-10-19"))
    run_report_job(scored_db, now=clock("2026-10-26"))
    assert scored_db.scalar("SELECT COUNT(*) FROM calibration_snapshots") == 2


def test_nothing_scored_stores_no_snapshot_and_still_reports() -> None:
    db = SqliteD1()
    seed_reference(db)
    seed_prediction(db)
    session = FakeSession()
    result = run_report_job(db, sender=sender(session), send=True, now=clock("2026-10-19"))
    assert result.exit_code == ExitCode.OK
    assert db.scalar("SELECT COUNT(*) FROM calibration_snapshots") == 0
    assert "No predictions have been scored yet." in str(result.summary["text"])
    assert [c[0].rsplit("/", 1)[1] for c in session.calls] == ["sendMessage"]  # no chart


def test_send_delivers_the_text_and_then_the_chart(scored_db: SqliteD1) -> None:
    session = FakeSession()
    result = run_report_job(scored_db, sender=sender(session), send=True, now=clock("2026-10-19"))
    assert result.exit_code == ExitCode.OK and result.summary["sent"] is True
    methods = [c[0].rsplit("/", 1)[1] for c in session.calls]
    assert methods == ["sendMessage", "sendPhoto"]
    assert session.calls[0][1]["json"]["chat_id"] == "1001"
    assert "Weekly report" in session.calls[0][1]["json"]["text"]
    photo = session.calls[1][1]["files"]["photo"]
    assert photo[1][:4] == b"\x89PNG" and photo[2] == "image/png"


def test_send_without_a_sender_is_a_configuration_error_and_nothing_is_stored(
    scored_db: SqliteD1,
) -> None:
    result = run_report_job(scored_db, send=True, now=clock("2026-10-19"))
    assert result.exit_code == ExitCode.DATA and "TELEGRAM" in str(result.summary["error"])
    assert scored_db.scalar("SELECT COUNT(*) FROM calibration_snapshots") == 0


def test_monday_only_reports_on_monday_and_skips_other_days(scored_db: SqliteD1) -> None:
    session = FakeSession()
    skipped = run_report_job(
        scored_db, sender=sender(session), send=True, monday_only=True, now=clock("2026-10-20")
    )  # a Tuesday
    assert skipped.summary["skipped"] == "not a Monday" and session.calls == []
    assert scored_db.scalar("SELECT COUNT(*) FROM calibration_snapshots") == 0
    monday = run_report_job(
        scored_db, sender=sender(session), send=True, monday_only=True, now=clock("2026-10-19")
    )
    assert monday.summary["sent"] is True and len(session.calls) == 2


def test_a_telegram_outage_keeps_the_snapshot_and_exits_with_the_outage_code(
    scored_db: SqliteD1,
) -> None:
    session = FakeSession(statuses=[500, 500])
    result = run_report_job(
        scored_db,
        sender=sender(session),
        send=True,
        now=clock("2026-10-19"),
    )
    assert result.exit_code == ExitCode.SOURCE_OUTAGE
    assert "123456:TEST" not in json.dumps(result.summary)
    assert scored_db.scalar("SELECT COUNT(*) FROM calibration_snapshots") == 1


def test_a_chart_failure_does_not_stop_the_text(
    scored_db: SqliteD1, monkeypatch: pytest.MonkeyPatch
) -> None:
    import footy.report.job as job

    def boom(_metrics: object) -> bytes:
        raise RuntimeError("no display")

    monkeypatch.setattr(job, "render_chart", boom)
    session = FakeSession()
    result = run_report_job(scored_db, sender=sender(session), send=True, now=clock("2026-10-19"))
    assert result.exit_code == ExitCode.OK and result.summary["chart"] == "failed"
    assert [c[0].rsplit("/", 1)[1] for c in session.calls] == ["sendMessage"]


def test_score_then_report_end_to_end() -> None:
    db = SqliteD1()
    seed_reference(db)
    seed_prediction(db, home=1, away=2)
    seed_match(db, home=1, away=2, goals=(2, 0))
    run_score_job(db, now=clock("2026-10-18"))
    rows = PredictionsRepo(db).scored_for_report()
    assert len(rows) == 1 and rows[0].rps_1x2 == pytest.approx(0.145)
    result = run_report_job(db, now=clock("2026-10-19"))
    assert result.summary["n_scored"] == 1


def test_reuploading_an_unchanged_file_does_not_move_the_omission_rate() -> None:
    """Review finding: omissions are stored per upload but predictions once per fixture, so the
    rate climbed with every re-upload. Both sides are now counted per upload."""
    db = SqliteD1()
    seed_reference(db)

    def upload(update_id: int) -> None:
        db.conn.execute(
            "INSERT INTO uploads (update_id, received_at, status, n_published, n_omitted) "
            "VALUES (?, 't', 'processed', 3, 1)",
            (update_id,),
        )
        upload_id = db.scalar("SELECT MAX(upload_id) FROM uploads")
        db.conn.execute(
            "INSERT INTO omissions (upload_id, label, reason_code) VALUES (?, 'x', 'NO_FORECAST')",
            (upload_id,),
        )

    repo = PredictionsRepo(db)

    def rate() -> float:
        omitted = sum(repo.omission_counts().values())
        return omitted / (repo.published_total() + omitted)

    upload(1)
    first = rate()
    upload(2)
    upload(3)
    assert first == pytest.approx(0.25) and rate() == pytest.approx(0.25)
    db.conn.execute(
        "INSERT INTO uploads (update_id, received_at, status) VALUES (9, 't', 'rejected')"
    )
    assert rate() == pytest.approx(0.25)  # rejected uploads are not counted
