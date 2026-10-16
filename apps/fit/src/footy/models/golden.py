"""Golden vectors: the training-serving-skew control (architecture sections 8.1 and 9.5).

Each file in ``packages/contracts/golden`` holds synthetic inputs of one grid builder with the grid
cells and markets the Python reference produces. The TypeScript engine must match them cell by cell
within ``TOLERANCE`` (no cross-language hash). Only made-up inputs appear here; no source data.

    python -m footy.models.golden --write   regenerate the files
    python -m footy.models.golden --check   fail if a committed file differs from the code
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from footy.config import REPO_ROOT
from footy.models.grid import (
    Grid,
    bivariate_poisson_grid,
    clip_rate,
    dixon_coles_grid,
    feasible_rho,
    independent_grid,
    markets,
)
from footy.models.pi_rating import PiParams, pi_rates

GOLDEN_DIR = REPO_ROOT / "packages" / "contracts" / "golden"
SCHEMA_VERSION = 1
TOLERANCE = 1e-9

Inputs = Mapping[str, float]
Builder = Callable[[Inputs], tuple[dict[str, float], Grid]]


def _dc(inputs: Inputs) -> tuple[dict[str, float], Grid]:
    """Dixon-Coles as the model serves it: rates clipped to the supported range and rho clamped to
    the interval where every correction factor stays positive (``DcModel.grid``)."""
    lam1, lam2 = clip_rate(inputs["lambda_home"]), clip_rate(inputs["lambda_away"])
    rho = feasible_rho(lam1, lam2, inputs["rho"])
    return {"lambda_home": lam1, "lambda_away": lam2, "rho": rho}, dixon_coles_grid(lam1, lam2, rho)


def _pi(inputs: Inputs) -> tuple[dict[str, float], Grid]:
    """Pi-rating as the model serves it: ratings -> expected goal difference -> goal rates (the
    mapping hypothesis of ADR-006) -> clipped -> independent Poisson grid."""
    lam1, lam2 = pi_rates(
        inputs["home_rating"],
        inputs["away_rating"],
        inputs["diff_scale"],
        inputs["league_total"],
        PiParams(),
    )
    lam1, lam2 = clip_rate(lam1), clip_rate(lam2)
    return {"lambda_home": lam1, "lambda_away": lam2}, independent_grid(lam1, lam2)


def _bp(inputs: Inputs) -> tuple[dict[str, float], Grid]:
    """Bivariate Poisson as the model serves it: all three rates clipped to the supported range."""
    lam1, lam2 = clip_rate(inputs["lambda1"]), clip_rate(inputs["lambda2"])
    lam3 = clip_rate(inputs["lambda3"])
    return {"lambda1": lam1, "lambda2": lam2, "lambda3": lam3}, bivariate_poisson_grid(
        lam1, lam2, lam3
    )


BUILDERS: dict[str, Builder] = {"dc": _dc, "pi": _pi, "bp": _bp}

INPUTS: dict[str, list[dict[str, float]]] = {
    "dc": [
        {"lambda_home": 1.45, "lambda_away": 1.10, "rho": -0.08},  # a typical fixture
        {"lambda_home": 1.10, "lambda_away": 1.45, "rho": -0.08},  # the mirror image
        {"lambda_home": 1.30, "lambda_away": 1.30, "rho": 0.0},  # no correction
        {"lambda_home": 0.60, "lambda_away": 0.50, "rho": -0.12},  # a tight low-scoring game
        {"lambda_home": 2.60, "lambda_away": 0.55, "rho": -0.05},  # a heavy favourite
        {"lambda_home": 2.20, "lambda_away": 2.10, "rho": 0.03},  # an open game, positive rho
        {"lambda_home": 0.30, "lambda_away": 2.00, "rho": -0.10},  # strong away side
        {"lambda_home": 4.70, "lambda_away": 3.40, "rho": 0.087},  # rho clamped to stay feasible
        {"lambda_home": 90.0, "lambda_away": 0.001, "rho": -0.2},  # rates clipped to 6.0 / 0.01
    ],
    "pi": [
        {"home_rating": 0.6, "away_rating": -0.3, "diff_scale": 0.5, "league_total": 2.8},
        {"home_rating": 0.0, "away_rating": 0.0, "diff_scale": 0.5, "league_total": 2.6},
        {"home_rating": -0.5, "away_rating": 0.4, "diff_scale": 0.8, "league_total": 2.7},
        {"home_rating": 1.2, "away_rating": -1.0, "diff_scale": 0.6, "league_total": 3.1},
        {
            "home_rating": 3.0,
            "away_rating": -3.0,
            "diff_scale": 1.0,
            "league_total": 2.5,
        },  # floored
        {
            "home_rating": 0.2,
            "away_rating": 0.1,
            "diff_scale": 0.3,
            "league_total": 90.0,
        },  # clipped
    ],
    "bp": [
        {"lambda1": 1.45, "lambda2": 1.10, "lambda3": 0.10},
        {"lambda1": 1.10, "lambda2": 1.45, "lambda3": 0.10},
        {"lambda1": 1.30, "lambda2": 1.30, "lambda3": 0.0005},  # almost no covariance
        {"lambda1": 0.70, "lambda2": 0.60, "lambda3": 0.25},
        {"lambda1": 2.40, "lambda2": 0.60, "lambda3": 0.15},
        {"lambda1": 2.00, "lambda2": 2.00, "lambda3": 0.60},
        {"lambda1": 90.0, "lambda2": 0.001, "lambda3": 9.0},  # rates clipped
    ],
}


def build(model: str) -> dict[str, object]:
    builder = BUILDERS[model]
    vectors: list[dict[str, object]] = []
    for inputs in INPUTS[model]:
        effective, grid = builder(inputs)
        vectors.append(
            {
                "inputs": dict(inputs),
                "effective_inputs": effective,
                "grid": [[float(v) for v in row] for row in grid],
                "markets": markets(grid).as_dict(),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "model": model,
        "tolerance": TOLERANCE,
        "note": "Synthetic inputs. grid[i][j] = P(home scores i, away scores j), 0 <= i, j <= 12.",
        "vectors": vectors,
    }


def same(a: object, b: object, tol: float = 1e-12) -> bool:
    """Structural equality with a tiny numeric tolerance (``exp`` may differ in the last bit between
    platforms; the contract itself is ``TOLERANCE``)."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k], tol) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y, tol) for x, y in zip(a, b, strict=True))
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, int | float) and isinstance(b, int | float):
        return abs(a - b) <= tol
    return a == b


def path_for(model: str) -> Path:
    return GOLDEN_DIR / f"{model}_grid_v{SCHEMA_VERSION}.json"


def render(model: str) -> str:
    return json.dumps(build(model), indent=1) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="footy.models.golden")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    status = 0
    for model in sorted(BUILDERS):
        path = path_for(model)
        text = render(model)
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {path.name}")
        elif not path.exists() or not same(
            json.loads(path.read_text(encoding="utf-8")), build(model)
        ):
            print(f"{path.name} is out of date: run with --write", file=sys.stderr)
            status = 1
    return status


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
