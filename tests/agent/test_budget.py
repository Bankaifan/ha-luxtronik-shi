"""API budget guard: low core or graphql budget makes background scripts skip a tick; unreadable is not low."""
import json

import budget


def rl(core=5000, gql=5000, limit=5000):
    res = {"core": {"limit": limit, "remaining": core, "reset": 0}, "graphql": {"limit": limit, "remaining": gql, "reset": 0}}
    return lambda *a: json.dumps({"resources": res})


def test_enough_budget_is_not_low():
    assert budget.low(budget.BACKGROUND, rl(core=1300)) is None


def test_low_core_or_graphql_is_named():
    assert budget.low(budget.BACKGROUND, rl(core=1000)).startswith("GitHub API budget low (core 1000/5000")
    assert "graphql 10/5000" in budget.low(budget.START, rl(gql=10))
    assert budget.low(budget.START, rl(core=1000)) is None


def test_unreadable_budget_carries_on():
    def boom(*a):
        raise RuntimeError("down")
    assert budget.low(budget.BACKGROUND, boom) is None
