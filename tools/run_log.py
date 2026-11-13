"""Write the last lines of a failed run's log to ci-failure.log (git-ignored) for a model run to Read.

A large `gh run view --log-failed` output lands in a tool-results file under ~/.claude that the judge settings deny
(#604, #608, #612); pipes are not on the allow list. Usage: python3 tools/run_log.py <run id> [lines, default 400].
"""
import sys

import ghcall

OUT = "ci-failure.log"


def main(argv, gh=ghcall.gh):
    if not argv or not argv[0].isdigit():
        raise SystemExit("usage: run_log.py <run id> [lines]")
    lines = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 400
    try:
        text = gh("run", "view", argv[0], "--log-failed")
    except ghcall.GhError as e:
        text = f"log not available: {e}\n"
    tail = text.splitlines()[-lines:]
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(tail) + "\n")
    return f"{OUT}: {len(tail)} lines of run {argv[0]}"


if __name__ == "__main__":
    print(main(sys.argv[1:]))
