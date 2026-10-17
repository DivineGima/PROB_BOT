"""Promotion gate (architecture section 8.6, ADR-030). Pure: it reads a snapshot of a candidate run
and returns every reason it fails, so a rejected run explains itself.

Structural checks:

1. the run is still ``building``;
2. at least one model is ``ok``, and every model the run attempted has a ``model_params`` row;
3. ``team_form`` covers at least 95% of the active teams;
4. every ``ok`` payload parses, carries the version this code understands, and its SHA-256 matches
   the stored hash (read back from the database, not from memory);
5. row counts are plausible: the run recorded how many teams had training matches, and each ``ok``
   payload holds at least 95% of them. A run that did not record that number fails: the check
   cannot be skipped by omitting it;
6. every forecast the run recorded is stored: the run recorded how many fixtures it forecast
   (``n_forecast_fixtures``) and at least that many ``fixture_forecasts`` rows exist (version 2,
   ADR-042). A run that did not record the number fails, like the check above; a run with no
   fixtures in its window records 0 and passes.

Forecast carry-over (version 2, unvalidated): versus the active run, the new run must forecast at
least ``forecast_carryover`` of the fixtures the active run forecast for today or later. Without it
a fit that found no upcoming fixtures (ingest not yet run, a feed gap) would record zero forecasts,
pass check 6 and replace a run that still serves the next days. Skipped, like the stability guard,
by the explicit ``--accept-drift`` override.

Stability guard (unvalidated): versus the active run, no team's attack/defence (``dc``, ``bp``) or
home/away rating (``pi``) moves by more than ``stability_bound``. The active run's payloads must
themselves verify (the caller passes only verified ones and lists the rest in ``active_skipped``,
and the guard is skipped for those models with the reason recorded). ``check_stability=False`` is
the explicit, logged ``--accept-drift`` override; the structural checks still apply. There is
deliberately NO performance comparison with the active run: the new run's window includes the most
recent days, so such a comparison would be in-sample (ADR-030).
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from footy.config import (
    GATE_FORECAST_CARRYOVER,
    GATE_FORM_COVERAGE,
    GATE_PAYLOAD_COVERAGE,
    STABILITY_BOUND,
)
from footy.models.registry import team_values
from footy.payload import payload_sha256
from footy.repo.models import STATUS_BUILDING, ParamRow

SUPPORTED_PAYLOAD_VERSION = 1


@dataclass(frozen=True)
class GateInput:
    run_status: str
    attempted_models: Sequence[str]
    params: Sequence[ParamRow]
    form_rows: int  # team_form rows of active teams
    active_teams: int
    n_teams_training: int | None  # teams with training matches, from the run's diagnostics
    expected_forecasts: int | None = None  # fixtures forecast, from the run's diagnostics (v2)
    forecast_rows: int = 0  # fixture_forecasts rows stored for the run (v2)
    active_future_forecasts: int = 0  # upcoming fixtures the active run forecast (v2)
    carried_forecasts: int = 0  # of those, how many the new run forecast too (v2)
    forecast_carryover: float = GATE_FORECAST_CARRYOVER
    active_payloads: Mapping[str, dict[str, object]] = field(default_factory=dict)
    active_skipped: Mapping[str, str] = field(default_factory=dict)  # model -> why not compared
    stability_bound: float = STABILITY_BOUND
    form_coverage: float = GATE_FORM_COVERAGE
    payload_coverage: float = GATE_PAYLOAD_COVERAGE
    check_stability: bool = True


@dataclass(frozen=True)
class GateResult:
    passed: bool
    reasons: list[str]
    checks: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {"passed": self.passed, "reasons": self.reasons, "checks": self.checks}


def decode_payload(row: ParamRow) -> tuple[dict[str, object] | None, str | None]:
    """The payload of an ``ok`` row if its hash and shape verify; otherwise (None, reason)."""
    if row.payload_json is None or row.payload_sha256 is None:
        return None, f"{row.model}: an ok model has no payload or hash"
    if payload_sha256(row.payload_json) != row.payload_sha256:
        return None, f"{row.model}: payload hash does not verify (corrupted or altered)"
    try:
        payload = json.loads(row.payload_json)
    except ValueError:
        return None, f"{row.model}: payload is not valid JSON"
    if not isinstance(payload, dict) or payload.get("payload_version") != SUPPORTED_PAYLOAD_VERSION:
        return None, f"{row.model}: payload version is not {SUPPORTED_PAYLOAD_VERSION}"
    if not isinstance(payload.get("teams"), dict):
        return None, f"{row.model}: payload has no team table"
    return payload, None


def evaluate_gate(gate: GateInput) -> GateResult:
    reasons: list[str] = []
    checks: dict[str, object] = {}

    checks["status_building"] = gate.run_status == STATUS_BUILDING
    if not checks["status_building"]:
        reasons.append(f"run status is {gate.run_status!r}, not 'building'")

    by_model = {p.model: p for p in gate.params}
    ok_rows = [p for p in gate.params if p.status == "ok"]
    checks["models_ok"] = [p.model for p in ok_rows]
    if not ok_rows:
        reasons.append("no model is ok")
    missing = [m for m in gate.attempted_models if m not in by_model]
    if missing:
        reasons.append(f"no model_params row for: {', '.join(sorted(missing))}")

    coverage = gate.form_rows / gate.active_teams if gate.active_teams else 0.0
    checks["team_form_coverage"] = round(coverage, 4)
    if gate.active_teams == 0 or coverage < gate.form_coverage:
        reasons.append(
            f"team_form covers {gate.form_rows} of {gate.active_teams} active teams "
            f"(need {gate.form_coverage:.0%})"
        )

    if gate.n_teams_training is None or gate.n_teams_training < 1:
        reasons.append(
            "the run did not record how many teams had training matches "
            "(diagnostics.n_teams_training), so the payload coverage cannot be checked"
        )

    checks["forecast_rows"] = gate.forecast_rows
    checks["forecasts_expected"] = gate.expected_forecasts
    if gate.expected_forecasts is None:
        reasons.append(
            "the run did not record how many fixtures it forecast "
            "(diagnostics.n_forecast_fixtures), so the forecasts cannot be checked"
        )
    elif gate.forecast_rows < gate.expected_forecasts:
        reasons.append(
            f"only {gate.forecast_rows} of {gate.expected_forecasts} recorded forecasts are stored"
        )

    if gate.check_stability and gate.active_future_forecasts > 0:
        needed_carried = math.ceil(gate.forecast_carryover * gate.active_future_forecasts)
        checks["forecast_carryover"] = {
            "active_upcoming": gate.active_future_forecasts,
            "carried": gate.carried_forecasts,
            "needed": needed_carried,
        }
        if gate.carried_forecasts < needed_carried:
            reasons.append(
                f"the run forecasts only {gate.carried_forecasts} of the "
                f"{gate.active_future_forecasts} upcoming fixtures the active run forecasts "
                f"(need {gate.forecast_carryover:.0%})"
            )

    payloads: dict[str, dict[str, object]] = {}
    for row in ok_rows:
        payload, problem = decode_payload(row)
        if payload is None:
            reasons.append(problem or f"{row.model}: payload could not be read")
            continue
        payloads[row.model] = payload
        teams = payload["teams"]
        assert isinstance(teams, dict)  # noqa: S101 (checked by decode_payload)
        if gate.n_teams_training is not None and gate.n_teams_training >= 1:
            needed = gate.payload_coverage * gate.n_teams_training
            if len(teams) < needed:
                reasons.append(
                    f"{row.model}: payload holds {len(teams)} teams but {gate.n_teams_training} "
                    f"teams had training matches (need {gate.payload_coverage:.0%})"
                )
    checks["payload_hashes_verified"] = sorted(payloads)

    jumps: dict[str, object] = {}
    if not gate.check_stability:
        checks["stability_accepted"] = True  # explicit override; see the module docstring
    else:
        for model, payload in sorted(payloads.items()):
            if model in gate.active_skipped:
                jumps[model] = {"skipped": gate.active_skipped[model]}
                continue
            previous = gate.active_payloads.get(model)
            if previous is None:
                continue
            new_values, old_values = team_values(model, payload), team_values(model, previous)
            worst_team, worst = None, 0.0
            over = 0
            for team_id, values in new_values.items():
                if team_id not in old_values:
                    continue
                move = max(abs(a - b) for a, b in zip(values, old_values[team_id], strict=True))
                if move > gate.stability_bound:
                    over += 1
                if move > worst:
                    worst_team, worst = team_id, move
            jumps[model] = {"max_move": round(worst, 6), "team_id": worst_team, "over_bound": over}
            if over:
                reasons.append(
                    f"{model}: {over} team value(s) moved more than {gate.stability_bound} versus "
                    f"the active run (largest {worst:.3f}, team {worst_team})"
                )
    checks["stability"] = jumps
    return GateResult(not reasons, reasons, checks)
