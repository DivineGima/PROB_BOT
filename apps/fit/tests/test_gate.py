"""Promotion gate: every structural check and the stability guard, as pure functions (Stage 4)."""

from __future__ import annotations

import hashlib
import json

from footy.payload import payload_sha256, payload_text
from footy.publish.gate import GateInput, evaluate_gate
from footy.repo.models import ParamRow


def payload(model: str = "dc", teams: int = 20, shift: float = 0.0) -> dict[str, object]:
    return {
        "payload_version": 1,
        "model": model,
        "teams": {
            str(t): [0.1 * (t % 5) + (shift if t == 3 else 0.0), -0.05 * (t % 4), "EPL"]
            for t in range(1, teams + 1)
        },
    }


def row(model: str = "dc", **kwargs: object) -> ParamRow:
    text = payload_text(kwargs.pop("payload", payload(model)))  # type: ignore[arg-type]
    fields: dict[str, object] = {
        "model": model,
        "status": "ok",
        "payload_version": 1,
        "payload_json": text,
        "payload_sha256": payload_sha256(text),
        "error": None,
    }
    fields.update(kwargs)
    return ParamRow(**fields)  # type: ignore[arg-type]


def gate(**overrides: object) -> GateInput:
    base: dict[str, object] = {
        "run_status": "building",
        "attempted_models": ["dc", "pi", "bp"],
        "params": [row("dc"), row("pi"), row("bp")],
        "form_rows": 20,
        "active_teams": 20,
        "n_teams_training": 20,
        "expected_forecasts": 0,
    }
    base.update(overrides)
    return GateInput(**base)  # type: ignore[arg-type]


def test_a_healthy_run_passes() -> None:
    result = evaluate_gate(gate())
    assert result.passed and result.reasons == []
    assert result.checks["models_ok"] == ["dc", "pi", "bp"]
    assert result.checks["team_form_coverage"] == 1.0


def test_run_must_be_building() -> None:
    result = evaluate_gate(gate(run_status="rejected"))
    assert not result.passed and "not 'building'" in result.reasons[0]


def test_no_ok_model_fails() -> None:
    failed = [ParamRow(m, "failed", None, None, None, "boom") for m in ("dc", "pi", "bp")]
    result = evaluate_gate(gate(params=failed))
    assert not result.passed and "no model is ok" in result.reasons


def test_one_ok_model_is_enough_and_a_failed_model_is_not_a_gate_failure() -> None:
    params = [
        row("dc"),
        ParamRow("pi", "failed", None, None, None, "x"),
        ParamRow("bp", "failed", None, None, None, "y"),
    ]
    assert evaluate_gate(gate(params=params)).passed


def test_an_attempted_model_without_a_row_fails() -> None:
    result = evaluate_gate(gate(params=[row("dc"), row("pi")]))
    assert not result.passed and any("no model_params row for: bp" in r for r in result.reasons)


def test_form_coverage_threshold() -> None:
    assert evaluate_gate(gate(form_rows=19, active_teams=20)).passed  # exactly 95%
    low = evaluate_gate(gate(form_rows=18, active_teams=20))
    assert not low.passed and "team_form covers 18 of 20" in low.reasons[0]
    assert not evaluate_gate(gate(form_rows=0, active_teams=0)).passed


def test_a_corrupted_payload_fails_the_hash_check() -> None:
    good = row("dc")
    tampered = ParamRow(
        good.model,
        "ok",
        1,
        (good.payload_json or "").replace("0.1", "0.2", 1),
        good.payload_sha256,
        None,
    )
    result = evaluate_gate(gate(params=[tampered, row("pi"), row("bp")]))
    assert not result.passed and any("hash does not verify" in r for r in result.reasons)


def test_a_payload_that_is_not_json_or_has_the_wrong_version_or_shape() -> None:
    not_json = "{oops"
    bad_json = ParamRow(
        "dc", "ok", 1, not_json, hashlib.sha256(not_json.encode()).hexdigest(), None
    )
    assert any("not valid JSON" in r for r in evaluate_gate(gate(params=[bad_json])).reasons)

    version = payload()
    version["payload_version"] = 2
    assert any(
        "version" in r for r in evaluate_gate(gate(params=[row("dc", payload=version)])).reasons
    )

    no_teams = {"payload_version": 1, "model": "dc", "teams": []}
    assert any(
        "no team table" in r
        for r in evaluate_gate(gate(params=[row("dc", payload=no_teams)])).reasons
    )

    not_object = json.dumps([1, 2])
    odd = ParamRow("dc", "ok", 1, not_object, hashlib.sha256(not_object.encode()).hexdigest(), None)
    assert not evaluate_gate(gate(params=[odd])).passed


def test_an_ok_row_without_payload_or_hash_fails() -> None:
    result = evaluate_gate(gate(params=[ParamRow("dc", "ok", 1, None, None, None)]))
    assert any("no payload or hash" in r for r in result.reasons)


def test_a_payload_that_misses_many_teams_fails_the_row_count_check() -> None:
    thin = row("dc", payload=payload("dc", teams=10))
    result = evaluate_gate(gate(params=[thin, row("pi"), row("bp")], n_teams_training=20))
    assert not result.passed and any("payload holds 10 teams" in r for r in result.reasons)


def test_jumped_parameters_fail_the_stability_guard() -> None:
    previous = {"dc": payload("dc")}
    jumped = row("dc", payload=payload("dc", shift=1.2))
    result = evaluate_gate(gate(params=[jumped, row("pi"), row("bp")], active_payloads=previous))
    assert not result.passed
    reason = next(r for r in result.reasons if "moved more than" in r)
    assert "dc: 1 team value(s)" in reason and "team 3" in reason
    assert result.checks["stability"]["dc"]["over_bound"] == 1  # type: ignore[index]


def test_small_moves_new_teams_and_missing_previous_models_pass_the_guard() -> None:
    previous = {"dc": payload("dc", teams=18)}  # teams 19 and 20 are new
    small = row("dc", payload=payload("dc", shift=0.3))
    result = evaluate_gate(
        gate(params=[small, row("pi")], active_payloads=previous, attempted_models=["dc", "pi"])
    )
    assert result.passed
    assert "pi" not in result.checks["stability"]  # type: ignore[operator]  # no previous pi payload


def test_the_bound_is_configurable() -> None:
    previous = {"dc": payload("dc")}
    moved = row("dc", payload=payload("dc", shift=0.3))
    strict = evaluate_gate(
        gate(params=[moved], attempted_models=["dc"], active_payloads=previous, stability_bound=0.2)
    )
    assert not strict.passed


def test_all_reasons_are_reported_together() -> None:
    result = evaluate_gate(
        gate(run_status="rejected", form_rows=1, params=[row("dc", payload=payload("dc", teams=3))])
    )
    assert len(result.reasons) >= 3
    assert result.as_dict()["passed"] is False
