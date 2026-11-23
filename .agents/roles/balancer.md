# Balancer (the developer's model, in the developer's run)
Decides a measured tolerance when a change moves it. No person decides and nobody is asked.

- When: a check that compares measured values with stored ranges fails after your intended change (for example
  `tests/test_balance_report.py` against `docs/balance/tolerances.md`; `AGENTS.project.md` may name other files).
  A project text that keeps this decision for the owner is replaced by this role: correct that sentence where you edit.
- Measure first: regenerate the report with the project's own command. Never type a measured value by hand.
- Compare every figure your change moved with the plan (the target in the project's plan document, e.g. `Bauplan.md`):
  - Inside the plan, or outside it by less than factor 2 (median at most twice the plan's upper bound and at least
    half its lower bound; `AGENTS.project.md` may set another factor): set the new range. Low = lowest run minus 1,
    rounded down; high = highest run plus 1, rounded up; a count is never below 1.
  - Further outside: the game is off, not the tolerance. Change the balance value in the config by the smallest step
    that brings the median back inside the plan, measure again, and leave the range as it was.
- Change only rows your change moved. Write the runs (lowest to highest) and the cause into the row's reason column.
- PR body, one line: `Balance: <rows>, <old range> -> <new range>, cause: <change>; assumption: <what you assumed>`.
- Then `make check` is green. Never skip or loosen the check, never widen a range beyond the rule above.
