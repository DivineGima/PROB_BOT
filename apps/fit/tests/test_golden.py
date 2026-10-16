"""Golden vectors stay in step with the Python reference (Stage 3 step 7)."""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from footy.models import golden
from footy.models.grid import GRID_SIZE, OVER_LINES, dixon_coles_grid, markets


def _committed(model: str) -> dict[str, object]:
    return json.loads(golden.path_for(model).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_committed_files_match_what_the_code_produces() -> None:
    assert golden.main(["--check"]) == 0


def test_check_fails_when_a_file_is_stale(tmp_path: pytest.TempPathFactory, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(golden, "GOLDEN_DIR", tmp_path)
    assert golden.main(["--check"]) == 1  # missing file
    assert golden.main(["--write"]) == 0
    assert golden.main(["--check"]) == 0
    stale = json.loads(golden.path_for("dc").read_text(encoding="utf-8"))
    stale["vectors"][0]["grid"][0][0] += 1e-6
    golden.path_for("dc").write_text(json.dumps(stale), encoding="utf-8")
    assert golden.main(["--check"]) == 1


def test_every_vector_is_internally_consistent() -> None:
    data = _committed("dc")
    assert data["schema_version"] == 1
    assert data["tolerance"] == 1e-9
    vectors = data["vectors"]
    assert isinstance(vectors, list)
    assert len(vectors) >= 8
    for vector in vectors:
        grid = np.array(vector["grid"])
        assert grid.shape == (GRID_SIZE, GRID_SIZE)
        assert (grid >= 0).all()
        assert grid.sum() == pytest.approx(1.0, abs=1e-12)
        m = markets(grid)
        assert vector["markets"]["p_home"] == pytest.approx(m.p_home, abs=1e-12)
        assert len(vector["markets"]["overs"]) == len(OVER_LINES)
        assert sum(vector["markets"]["total_pmf"]) == pytest.approx(1.0, abs=1e-12)
        eff = vector["effective_inputs"]
        again = dixon_coles_grid(eff["lambda_home"], eff["lambda_away"], eff["rho"])
        assert np.abs(again - grid).max() < 1e-12


def test_vectors_cover_the_guard_cases() -> None:
    vectors = _committed("dc")["vectors"]
    assert isinstance(vectors, list)
    clamped = [v for v in vectors if v["effective_inputs"]["rho"] != v["inputs"]["rho"]]
    clipped = [
        v for v in vectors if v["effective_inputs"]["lambda_home"] != v["inputs"]["lambda_home"]
    ]
    assert clamped, "a vector must exercise the rho clamp"
    assert clipped, "a vector must exercise the rate clip"
    assert all(math.isfinite(v["effective_inputs"]["rho"]) for v in vectors)


def test_same_compares_with_tolerance() -> None:
    assert golden.same({"a": [1.0, 2.0]}, {"a": [1.0 + 1e-14, 2.0]})
    assert not golden.same({"a": [1.0]}, {"a": [1.1]})
    assert not golden.same({"a": 1}, {"b": 1})
    assert not golden.same([1], [1, 2])
    assert golden.same("x", "x")
    assert not golden.same(True, 1.0)
