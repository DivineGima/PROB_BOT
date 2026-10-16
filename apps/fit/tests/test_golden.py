"""Golden vectors stay in step with the Python reference (Stage 3 step 7)."""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from footy.models import golden
from footy.models.grid import GRID_SIZE, OVER_LINES, markets


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


@pytest.mark.parametrize("model", ["dc", "pi", "bp"])
def test_every_vector_is_internally_consistent(model: str) -> None:
    data = _committed(model)
    assert data["schema_version"] == 1 and data["model"] == model
    assert data["tolerance"] == 1e-9
    vectors = data["vectors"]
    assert isinstance(vectors, list)
    assert len(vectors) >= 6
    for vector in vectors:
        grid = np.array(vector["grid"])
        assert grid.shape == (GRID_SIZE, GRID_SIZE)
        assert (grid >= 0).all()
        assert grid.sum() == pytest.approx(1.0, abs=1e-12)
        m = markets(grid)
        assert vector["markets"]["p_home"] == pytest.approx(m.p_home, abs=1e-12)
        assert vector["markets"]["p_draw"] + vector["markets"]["p_away"] + vector["markets"][
            "p_home"
        ] == pytest.approx(1.0, abs=1e-12)
        assert len(vector["markets"]["overs"]) == len(OVER_LINES)
        assert sum(vector["markets"]["total_pmf"]) == pytest.approx(1.0, abs=1e-12)
        # the committed grid is what the reference builder gives for the committed inputs
        _effective, rebuilt = golden.BUILDERS[model](vector["inputs"])
        assert np.abs(rebuilt - grid).max() < 1e-12


def test_dc_vectors_cover_the_guard_cases() -> None:
    vectors = _committed("dc")["vectors"]
    assert isinstance(vectors, list)
    clamped = [v for v in vectors if v["effective_inputs"]["rho"] != v["inputs"]["rho"]]
    clipped = [
        v for v in vectors if v["effective_inputs"]["lambda_home"] != v["inputs"]["lambda_home"]
    ]
    assert clamped, "a vector must exercise the rho clamp"
    assert clipped, "a vector must exercise the rate clip"
    assert all(math.isfinite(v["effective_inputs"]["rho"]) for v in vectors)


def test_pi_vectors_cover_the_floor_and_the_clip() -> None:
    vectors = _committed("pi")["vectors"]
    assert isinstance(vectors, list)
    assert any(v["effective_inputs"]["lambda_away"] == 0.05 for v in vectors), "epsilon floor"
    assert any(v["effective_inputs"]["lambda_home"] == 6.0 for v in vectors), "rate clip"
    # a hand-checked case: ratings (0.6, -0.3), scale 0.5, total 2.8
    first = vectors[0]["effective_inputs"]
    d = 0.5 * 0.8438186042552807
    assert first["lambda_home"] == pytest.approx((2.8 + d) / 2, abs=1e-12)


def test_bp_vectors_cover_the_clip() -> None:
    vectors = _committed("bp")["vectors"]
    assert isinstance(vectors, list)
    assert any(v["effective_inputs"]["lambda3"] == 6.0 for v in vectors)
    assert vectors[0]["effective_inputs"] == vectors[0]["inputs"]  # normal inputs pass unchanged


def test_same_compares_with_tolerance() -> None:
    assert golden.same({"a": [1.0, 2.0]}, {"a": [1.0 + 1e-14, 2.0]})
    assert not golden.same({"a": [1.0]}, {"a": [1.1]})
    assert not golden.same({"a": 1}, {"b": 1})
    assert not golden.same([1], [1, 2])
    assert golden.same("x", "x")
    assert not golden.same(True, 1.0)
