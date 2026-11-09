import importlib.util
import pathlib

_path = pathlib.Path(__file__).parent.parent / "tools" / "tier.py"
_spec = importlib.util.spec_from_file_location("tier", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

HOT = {"week": "w", "code_lines": "6000", "modules": "10", "max_parallel_agent_prs": "3",
       "conflicts_rebuilt": "", "avg_review_rounds": "1.0", "median_ci_minutes": "5"}
COLD = {"week": "w", "code_lines": "100", "modules": "5", "max_parallel_agent_prs": "1",
        "conflicts_rebuilt": "", "avg_review_rounds": "1.0", "median_ci_minutes": "2"}


def weeks(*rows):
    return [{**r, "week": f"2026-0{i + 1}"} for i, r in enumerate(rows)]


def test_exceeded_counts_code_once_and_ignores_empty():
    assert mod.exceeded({**HOT, "modules": "40"}, "S") == ["code", "parallel PRs"]
    assert mod.exceeded(COLD, "S") == []


def test_two_exceeded_four_weeks_proposes():
    assert mod.propose(weeks(HOT, HOT, HOT, HOT), "S") == "M"


def test_only_one_exceeded_no_proposal():
    one = {**HOT, "max_parallel_agent_prs": "1"}
    assert mod.propose(weeks(one, one, one, one), "S") is None


def test_one_cold_week_breaks_streak():
    assert mod.propose(weeks(HOT, HOT, COLD, HOT), "S") is None
    assert mod.propose(weeks(COLD, HOT, HOT, HOT, HOT), "S") == "M"


def test_fewer_than_four_weeks_no_proposal():
    assert mod.propose(weeks(HOT, HOT, HOT), "S") is None


def test_m_uses_larger_thresholds_and_l_never_proposes():
    assert mod.propose(weeks(HOT, HOT, HOT, HOT), "M") is None
    big = {**HOT, "code_lines": "40000", "max_parallel_agent_prs": "6"}
    assert mod.propose(weeks(big, big, big, big), "M") == "L"
    assert mod.propose(weeks(big, big, big, big), "L") is None


def test_read_tier_defaults_to_s(tmp_path):
    assert mod.read_tier(tmp_path / "missing") == "S"
    f = tmp_path / "tier"
    f.write_text("m\n")
    assert mod.read_tier(f) == "M"
    f.write_text("x\n")
    assert mod.read_tier(f) == "S"
