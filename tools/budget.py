"""GitHub API budget guard (#511, #617): background scripts stand down while the token's budget is low.

About 2000 workflow runs an hour used up the author app's REST budget; every script then failed at random and the
failure watch turned each failure into an issue, which started more runs. A script that calls `low(floor)` first
skips its tick while less than FLOOR of the hourly budget is left; the next event or scheduled tick after the reset
does the work. `gh api rate_limit` itself does not count against the budget. Unreadable: not low (carry on).
"""
import datetime
import json

import ghcall

BACKGROUND = 0.25  # status, failure watch, orchestrator: leave the last quarter to merges and agent starts
START = 0.10  # dispatch: starting ready work stops only when the budget is nearly gone


def low(floor, run=ghcall.gh):
    """A one-line reason when core or graphql has less than FLOOR of its limit left, else None."""
    try:
        res = json.loads(run("api", "rate_limit"))["resources"]
    except Exception:  # noqa: BLE001 - an unreadable budget must never stop the work
        return None
    for name in ("core", "graphql"):
        r = res.get(name) or {}
        limit, left = int(r.get("limit") or 0), int(r.get("remaining") or 0)
        if limit and left < limit * floor:
            at = datetime.datetime.fromtimestamp(int(r.get("reset") or 0), datetime.UTC).strftime("%H:%M")
            return f"GitHub API budget low ({name} {left}/{limit}, reset {at} UTC): skipped, the next tick does the work"
    return None
