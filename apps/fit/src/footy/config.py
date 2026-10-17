"""Settings and constants for the fit job. The only module that reads environment variables for
Stage 2 (secrets are never logged and are hidden from ``repr``)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from footy.errors import ConfigError

REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = REPO_ROOT / "data"

SOURCE_FD_ORG = "fd_org"


@dataclass(frozen=True)
class Competition:
    comp_code: str
    name: str
    fd_code: str | None
    uk_div: str | None
    has_shots: int


# Section 5.2. The Scottish Premiership has no football-data.org code (free tier does not cover it)
# and is dropped under A-1 path 2 (ADR-035); the row still exists so the 179-club list stays whole.
COMPETITIONS: tuple[Competition, ...] = (
    Competition("EPL", "Premier League", "PL", "E0", 1),
    Competition("LL", "La Liga", "PD", "SP1", 1),
    Competition("BL", "Bundesliga", "BL1", "D1", 1),
    Competition("SA", "Serie A", "SA", "I1", 1),
    Competition("L1", "Ligue 1", "FL1", "F1", 1),
    Competition("UCL", "Champions League", "CL", None, 0),
    Competition("ERE", "Eredivisie", "DED", "N1", 1),
    Competition("PPL", "Primeira Liga", "PPL", "P1", 1),
    Competition("CHA", "Championship", "ELC", "E1", 1),
    Competition("SPL", "Scottish Premiership", None, "SC0", 1),
)
COMP_BY_FD_CODE: dict[str, Competition] = {c.fd_code: c for c in COMPETITIONS if c.fd_code}
FD_COMPETITIONS: tuple[Competition, ...] = tuple(c for c in COMPETITIONS if c.fd_code)

# football-data.org free tier: 10 requests/minute; stay clear of it (section 8.5).
MIN_REQUEST_INTERVAL_S = 6.5
INGEST_DAYS_BACK = 7
INGEST_DAYS_FORWARD = 3
BOOTSTRAP_SEASONS = 3
MAX_DISAGREEMENTS = 3
EVENT_DEDUPE_HOURS = 24

# Model run settings (architecture sections 5.4, 8.3, 8.4, 8.6). All are starting values and are
# snapshotted into ``model_runs.config_json``; none is validated yet.
MIN_TEAM_MATCHES = 10  # fewer training matches than this -> INSUFFICIENT_HISTORY (FR-10)
DRIFT_THRESHOLD_GOALS = 0.6  # goals per match, ADR-021 (goals only in v1, ADR-026)
STALE_HOURS = 36  # STALE MODELS banner age (ADR-015)
STABILITY_BOUND = 0.5  # promotion gate: largest allowed move of a team value versus the active run
GATE_FORM_COVERAGE = 0.95  # team_form must cover this share of active teams
GATE_PAYLOAD_COVERAGE = 0.95  # a payload must cover this share of teams with training matches
ENSEMBLE_KAPPA = 100.0  # softmax sharpness on mean RPS (RPS differences between models are tiny)
ENSEMBLE_RECENT = 200  # most recent scored predictions used for the rolling RPS
ENSEMBLE_SHRINK_N = 50  # pseudo-count of the prior in the weight shrinkage
RUNS_KEPT = 30  # retained model runs (ADR-004)
FORECAST_HORIZON_DAYS = 4  # forecast fixtures from today to today + this many days (ADR-042)
FORECAST_RUNS_KEPT = 5  # runs whose forecasts are kept; a rollback needs them (section 8.11)
DRIFT_TOLERANCE = 1e-9  # a goal difference of exactly the threshold passes
BACKTEST_REGRESSION_TOLERANCE = 0.003  # RPS rise versus the previous comparable backtest (ADR-046)
REPORT_TARGET_SCORED = 300  # PRD success metric: at least this many scored predictions
NO_RESULT_DAYS = 3  # a pending prediction with no result this long after kickoff is void (ADR-028)


@dataclass(frozen=True)
class Settings:
    fd_org_token: str = field(default="", repr=False)
    source_enabled_fdorg: bool = False
    cf_account_id: str = ""
    d1_database_id: str = ""
    cf_d1_token: str = field(default="", repr=False)

    def require_fd_org(self) -> str:
        """The legal gate (CLAUDE.md section 4): refuse unless the flag is on and a token exists."""
        if not self.source_enabled_fdorg:
            raise ConfigError(
                "SOURCE_ENABLED_FDORG is not '1': football-data.org stays off until the legal "
                "register entry is signed and the flag is set"
            )
        if not self.fd_org_token:
            raise ConfigError("FD_ORG_TOKEN is not set")
        return self.fd_org_token

    def require_d1(self) -> tuple[str, str, str]:
        missing = [
            name
            for name, value in (
                ("CF_ACCOUNT_ID", self.cf_account_id),
                ("D1_DATABASE_ID", self.d1_database_id),
                ("CF_D1_TOKEN", self.cf_d1_token),
            )
            if not value
        ]
        if missing:
            raise ConfigError(f"missing environment variable(s): {', '.join(missing)}")
        return self.cf_account_id, self.d1_database_id, self.cf_d1_token


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    source = os.environ if env is None else env
    return Settings(
        fd_org_token=source.get("FD_ORG_TOKEN", "").strip(),
        source_enabled_fdorg=source.get("SOURCE_ENABLED_FDORG", "").strip() == "1",
        cf_account_id=source.get("CF_ACCOUNT_ID", "").strip(),
        d1_database_id=source.get("D1_DATABASE_ID", "").strip(),
        cf_d1_token=source.get("CF_D1_TOKEN", "").strip(),
    )
