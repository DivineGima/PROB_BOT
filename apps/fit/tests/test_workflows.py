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


def steps(text: str) -> list[str]:
    """The text of each job step (a step starts at a line indented six spaces with a dash)."""
    blocks: list[list[str]] = []
    for line in text.splitlines():
        if line.startswith("      - "):
            blocks.append([line])
        elif blocks and (line.startswith("        ") or not line.strip()):
            blocks[-1].append(line)
        elif blocks and not line.startswith(" "):
            break
    return ["\n".join(b) for b in blocks]


def step_named(text: str, name: str) -> str:
    return next(s for s in steps(text) if f"name: {name}" in s)


def test_the_nightly_job_runs_the_steps_in_order_and_ends_with_the_alerts() -> None:
    text = (WORKFLOWS / "nightly.yml").read_text(encoding="utf-8")
    commands = [
        "footy.cli ingest",
        "footy.cli score",
        "footy.cli fit",
        "footy.cli publish",
        "footy.cli report --send --monday-only",
        "footy.cli healthcheck",
        "footy.cli alert --flush",
        "footy.cli alert --key",
    ]
    positions = [text.index(c) for c in commands]
    assert positions == sorted(positions)
    assert "if: always()" in step_named(text, "Send the alerts raised tonight")
    failure = step_named(text, "Alert that the nightly job failed")
    # an unhealthy night is explained by its own alert; no second "failed" message for it
    assert "if: failure() && steps.health.outcome != 'failure'" in failure
    assert "id: health" in step_named(text, "Health check")


def test_the_nightly_schedule_is_off_the_hour_switchable_and_cannot_overlap_a_manual_run() -> None:
    text = (WORKFLOWS / "nightly.yml").read_text(encoding="utf-8")
    cron = next(line for line in text.splitlines() if "cron:" in line)
    fields = cron.split('"')[1].split()
    assert fields == ["17", "1", "*", "*", "*"]  # 01:17 UTC (A-3)
    assert "vars.NIGHTLY_ENABLED == 'true'" in text, "the schedule needs the switch"
    assert "github.ref == 'refs/heads/main'" in text
    assert "group: footy-data" in text and "cancel-in-progress: false" in text
    assert "timeout-minutes: 45" in text
    assert "workflow_dispatch" in text
    assert "pull_request_target" not in text and "contents: read" in text


def test_the_nightly_secrets_reach_only_the_steps_that_need_them() -> None:
    text = (WORKFLOWS / "nightly.yml").read_text(encoding="utf-8")
    job_env = text.split("    env:\n", 1)[1].split("    defaults:", 1)[0]
    for name in ("CF_ACCOUNT_ID", "D1_DATABASE_ID", "CF_D1_TOKEN"):
        assert f"secrets.{name}" in job_env
    for name in ("FD_ORG_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "CF_DEPLOY_TOKEN"):
        assert name not in job_env, f"{name} must not be a job-level secret"
    assert "CF_DEPLOY_TOKEN" not in text

    wants_football_data = {"Ingest results and fixtures"}
    wants_telegram = {
        "Weekly report (Mondays)",
        "Send the alerts raised tonight",
        "Alert that the nightly job failed",
    }
    for step in steps(text):
        label = next(
            (ln.split("name:", 1)[1].strip() for ln in step.splitlines() if "name:" in ln), ""
        )
        assert ("secrets.FD_ORG_TOKEN" in step) == (label in wants_football_data), label
        for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
            assert (f"secrets.{name}" in step) == (label in wants_telegram), f"{label}: {name}"


def test_the_nightly_job_tolerates_only_the_documented_partial_outcomes() -> None:
    text = (WORKFLOWS / "nightly.yml").read_text(encoding="utf-8")
    ingest = step_named(text, "Ingest results and fixtures")
    fit = step_named(text, "Fit the models and store the forecasts")
    assert '"$rc" -eq 3' in ingest and "exit" in ingest  # a source outage, nothing else
    assert '"$rc" -eq 4' in fit and "exit" in fit  # a partial fit, nothing else
    for name in ("Score predictions", "Publish the run", "Health check"):
        assert "||" not in step_named(text, name), f"{name} must fail the job when it fails"


def test_the_weekly_backup_has_the_database_token_only() -> None:
    text = (WORKFLOWS / "backup.yml").read_text(encoding="utf-8")
    assert "secrets.CF_D1_TOKEN" in text and "secrets.CF_ACCOUNT_ID" in text
    for name in ("FD_ORG_TOKEN", "TELEGRAM", "CF_DEPLOY_TOKEN"):
        assert name not in text
    cron = next(line for line in text.splitlines() if "cron:" in line)
    assert cron.split('"')[1].split()[0] not in ("0", "00")
    assert "github.ref == 'refs/heads/main'" in text and "contents: read" in text
    assert "group: footy-data" in text, "the export blocks the database: never beside a nightly"
    assert "retention-days: 30" in text and "if-no-files-found: error" in text
    for line in text.splitlines():
        if "uses:" in line:
            assert "@" in line and len(line.split("@")[1].split()[0]) == 40, f"pin by SHA: {line}"


def test_every_action_in_every_workflow_is_pinned_to_a_commit() -> None:
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(("- uses:", "uses:")):
                ref = line.split("@", 1)[1].split()[0]
                assert len(ref) == 40, f"{path.name}: {line.strip()}"


def test_the_inputs_reach_the_shell_only_as_environment_variables() -> None:
    for name in ("data.yml", "backtest.yml", "nightly.yml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        run_blocks = [line for line in text.splitlines() if "python -m footy" in line]
        assert run_blocks
        assert not any("${{" in line for line in run_blocks), f"{name}: interpolation in a run line"
