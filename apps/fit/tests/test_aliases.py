"""Normaliser, resolver and the real reference files (Stage 2 step 2 and 3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from footy.aliases import Resolver, load_reference, normalise
from footy.config import DATA_DIR
from footy.errors import DataError

# Counts from the PRD table (Essentials Stage 2 step 2). Update together with the summer rollover.
EXPECTED_ACTIVE = {
    "EPL": 20,
    "LL": 20,
    "BL": 18,
    "SA": 20,
    "L1": 18,
    "ERE": 18,
    "PPL": 18,
    "CHA": 24,
    "SPL": 12,
}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Arsenal FC", "arsenal"),
        ("AFC Bournemouth", "bournemouth"),
        ("  Real   Madrid  CF ", "real madrid cf"),
        ("Atlético Madrid", "atletico madrid"),
        ("Bayern München", "bayern munchen"),
        ("Borussia Mönchengladbach", "borussia monchengladbach"),
        ("Paris Saint-Germain", "paris saint germain"),
        ("Brighton & Hove Albion FC", "brighton hove albion"),
        ("FK Bodø/Glimt", "fk bodo glimt"),
        ("Fenerbahçe SK", "fenerbahce sk"),
        ("1. FC Köln", "1 koln"),
        ("St. Pauli", "st pauli"),
        ("Hamburger SV", "hamburger sv"),
        ("FC Twente '65", "twente 65"),
        ("FC", "fc"),  # a name made only of dropped tokens is kept, not emptied
        ("", ""),
        ("***", ""),
    ],
)
def test_normalise_hand_written_variants(raw: str, expected: str) -> None:
    assert normalise(raw) == expected


def test_normalise_is_idempotent_and_rejects_non_strings() -> None:
    for name in ["Arsenal FC", "Atlético Madrid", "1. FC Köln", "Bodø/Glimt"]:
        once = normalise(name)
        assert normalise(once) == once
    with pytest.raises(TypeError):
        normalise(None)  # type: ignore[arg-type]


def test_resolver_returns_none_for_unknown_or_bad_input() -> None:
    resolver = Resolver("fd_org", {"arsenal": 1})
    assert resolver.resolve("Arsenal FC") == 1
    assert resolver.resolve("Arsenal") == 1
    assert resolver.resolve("Arsenal Women") is None
    assert resolver.resolve(None) is None
    assert resolver.resolve("") is None
    assert resolver.resolve(42) is None
    assert len(resolver) == 1


# -- the real files -------------------------------------------------------------------------------


def test_canonical_counts_match_the_prd_table() -> None:
    data = json.loads((DATA_DIR / "canonical_teams.json").read_text(encoding="utf-8"))
    counts = {c["code"]: len(c["teams"]) for c in data["competitions"]}
    assert counts == EXPECTED_ACTIVE
    assert len(data["ucl_only"]) == 11
    assert load_reference().active_count() == 179


def test_reference_has_history_only_clubs_inactive_and_no_overlap() -> None:
    ref = load_reference()
    inactive = [t for t in ref.teams if not t.active]
    assert 50 <= len(inactive) <= 70
    names = [t.canonical_name for t in ref.teams]
    assert len(names) == len(set(names))
    assert len({normalise(n) for n in names}) == len(names)


def test_every_team_resolves_from_its_own_name_for_every_source() -> None:
    ref = load_reference()
    for source, table in ref.aliases.items():
        resolver = Resolver(source, table)
        for team in ref.teams:
            assert resolver.resolve(team.canonical_name) == team.canonical_name
            assert resolver.resolve(f"{team.canonical_name} FC") == team.canonical_name


def test_alias_files_only_point_at_known_teams_and_never_collide() -> None:
    ref = load_reference()  # raises DataError on a collision or an unknown target
    table = ref.aliases["fd_org"]
    assert table[normalise("Brighton & Hove Albion FC")] == "Brighton"
    assert table[normalise("FC Internazionale Milano")] == "Inter Milan"
    assert table[normalise("Club Atlético de Madrid")] == "Atlético Madrid"
    # Different clubs that look alike stay different.
    assert table[normalise("Paris FC")] != table[normalise("Paris Saint-Germain FC")]
    assert table[normalise("Sheffield United FC")] != table[normalise("Sheffield Wednesday FC")]
    assert table[normalise("Manchester City FC")] != table[normalise("Manchester United FC")]


# -- loader error handling ------------------------------------------------------------------------


def _write(
    root: Path, canonical: object, historical: object, aliases: object | None = None
) -> Path:
    (root / "aliases").mkdir(parents=True)
    (root / "canonical_teams.json").write_text(json.dumps(canonical), encoding="utf-8")
    (root / "historical_teams.json").write_text(json.dumps(historical), encoding="utf-8")
    if aliases is not None:
        (root / "aliases" / "fd_org.json").write_text(json.dumps(aliases), encoding="utf-8")
    return root


GOOD_CANON = {
    "competitions": [{"code": "EPL", "teams": ["Arsenal", "Chelsea"]}],
    "ucl_only": ["Viking"],
}
GOOD_HIST = {"clubs": [{"canonical_name": "Luton Town", "last_competition": "CHA"}]}


def test_loader_accepts_a_minimal_valid_set(tmp_path: Path) -> None:
    ref = load_reference(_write(tmp_path, GOOD_CANON, GOOD_HIST))
    assert ref.active_count() == 3
    assert len(ref.teams) == 4


@pytest.mark.parametrize(
    ("canonical", "historical", "aliases", "message"),
    [
        (
            {"competitions": [{"code": "XXX", "teams": ["A"]}], "ucl_only": []},
            GOOD_HIST,
            None,
            "unknown competition",
        ),
        ({"competitions": [], "ucl_only": []}, GOOD_HIST, None, "non-empty list"),
        (
            {"competitions": [{"code": "EPL", "teams": ["Arsenal", "Arsenal FC"]}], "ucl_only": []},
            GOOD_HIST,
            None,
            "same team",
        ),
        (
            GOOD_CANON,
            {"clubs": [{"canonical_name": "Arsenal", "last_competition": "EPL"}]},
            None,
            "same team",
        ),
        (GOOD_CANON, {"clubs": "nope"}, None, "must be a list"),
        (
            GOOD_CANON,
            {"clubs": [{"canonical_name": "X", "last_competition": "ZZZ"}]},
            None,
            "unknown competition",
        ),
        (
            GOOD_CANON,
            GOOD_HIST,
            {"source": "fd_org", "aliases": {"Nobody": ["x"]}},
            "not a known canonical",
        ),
        (GOOD_CANON, GOOD_HIST, {"source": "fd_uk", "aliases": {}}, "'source' must be"),
        (
            GOOD_CANON,
            GOOD_HIST,
            {"source": "fd_org", "aliases": {"Arsenal": ["Chelsea FC"]}},
            "maps to both",
        ),
        (
            GOOD_CANON,
            GOOD_HIST,
            {"source": "fd_org", "aliases": {"Arsenal": "x"}},
            "must be a list",
        ),
        (
            {"competitions": [{"code": "EPL", "teams": [""]}], "ucl_only": []},
            GOOD_HIST,
            None,
            "non-empty team name",
        ),
    ],
)
def test_loader_rejects_bad_files(
    tmp_path: Path, canonical: object, historical: object, aliases: object, message: str
) -> None:
    root = _write(tmp_path, canonical, historical, aliases)
    with pytest.raises(DataError, match=message):
        load_reference(root)


def test_loader_reports_missing_and_invalid_json(tmp_path: Path) -> None:
    with pytest.raises(DataError, match="cannot read"):
        load_reference(tmp_path)
    (tmp_path / "canonical_teams.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(DataError, match="not valid JSON"):
        load_reference(tmp_path)
    (tmp_path / "canonical_teams.json").write_text("[1]", encoding="utf-8")
    with pytest.raises(DataError, match="JSON object"):
        load_reference(tmp_path)


# Spellings football-data.org actually used that the first bootstrap dry-run reported as unknown
# (2026-10-17). They are names only, not source data.
DRY_RUN_FINDINGS = {
    "CD Tondela": "Tondela",
    "ES Troyes AC": "Troyes",
    "FK Kairat": "Kairat Almaty",
    "FK Shakhtar Donetsk": "Shakhtar Donetsk",
    "LASK Linz": "LASK",
    "PAE AEK": "AEK Athens",
    "PAE Olympiakos SFP": "Olympiacos",
    "Paphos FC": "Pafos",
    "RC Deportivo La Coruña": "Deportivo A Coruña",
    "SBV Excelsior": "Excelsior",
    "SC Cambuur-Leeuwarden": "Cambuur",
    "SC Farense": "Farense",
    "SV 07 Elversberg": "Elversberg",
    "Sport Lisboa e Benfica": "Benfica",
    "Telstar 1963": "Telstar",
}


@pytest.mark.parametrize(("spelling", "canonical"), sorted(DRY_RUN_FINDINGS.items()))
def test_spellings_found_by_the_first_dry_run_resolve(spelling: str, canonical: str) -> None:
    resolver = Resolver("fd_org", load_reference().aliases["fd_org"])
    assert resolver.resolve(spelling) == canonical
