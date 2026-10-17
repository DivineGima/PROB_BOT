"""Least privilege in the workflows that reach the database (architecture sections 9.1 and 9.3).
The files are read as text: they contain no secrets, only references to them."""

from __future__ import annotations

from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[3] / ".github" / "workflows"


def env_lines(text: str) -> dict[str, str]:
    return {
        line.strip().split(":", 1)[0]: line
        for line in text.splitlines()
        if ":" in line and not line.strip().startswith("#")
    }


def test_only_the_report_command_receives_the_telegram_secrets() -> None:
    lines = env_lines((WORKFLOWS / "data.yml").read_text(encoding="utf-8"))
    for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        line = lines[name]
        assert "inputs.command == 'report'" in line, f"{name} must depend on the chosen command"
        assert f"secrets.{name}" in line
        for other in ("fit", "publish", "backtest", "ingest", "bootstrap", "score", "d1-probe"):
            assert f"'{other}'" not in line


def test_the_football_data_secrets_do_not_reach_score_or_report() -> None:
    lines = env_lines((WORKFLOWS / "data.yml").read_text(encoding="utf-8"))
    for name in ("FD_ORG_TOKEN", "SOURCE_ENABLED_FDORG"):
        assert '"score"' not in lines[name] and '"report"' not in lines[name]


def test_the_data_workflow_offers_and_runs_the_new_commands() -> None:
    text = (WORKFLOWS / "data.yml").read_text(encoding="utf-8")
    assert "          - score\n" in text and "          - report\n" in text
    assert "python -m footy.cli score" in text
    assert "python -m footy.cli report --send" in text


def test_the_monthly_backtest_has_the_database_only_and_reports_regressions() -> None:
    text = (WORKFLOWS / "backtest.yml").read_text(encoding="utf-8")
    lines = env_lines(text)
    assert "FD_ORG_TOKEN" not in text and "TELEGRAM" not in text and "CF_DEPLOY_TOKEN" not in text
    for name in ("CF_ACCOUNT_ID", "D1_DATABASE_ID", "CF_D1_TOKEN"):
        assert f"secrets.{name}" in lines[name]
    assert "--fail-on-regression" in text
    assert "--models dc,pi,bp" in text
    assert "contents: read" in text
    assert "github.ref == 'refs/heads/main'" in text
    assert "pull_request_target" not in text


def test_the_monthly_schedule_avoids_the_top_of_the_hour() -> None:
    text = (WORKFLOWS / "backtest.yml").read_text(encoding="utf-8")
    cron = next(line for line in text.splitlines() if "cron:" in line)
    minute = cron.split('"')[1].split()[0]
    assert minute not in ("0", "00"), "GitHub delays scheduled runs at the top of the hour"
    assert "workflow_dispatch" in text


def test_the_inputs_reach_the_shell_only_as_environment_variables() -> None:
    for name in ("data.yml", "backtest.yml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        run_blocks = [line for line in text.splitlines() if "python -m footy" in line]
        assert run_blocks
        assert not any("${{" in line for line in run_blocks), f"{name}: interpolation in a run line"
