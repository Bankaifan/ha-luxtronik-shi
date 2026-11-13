"""Orchestrator HANDOVER.md from the model run (design 0017, step 5).

The orchestrator model has no write tool. When HANDOVER.md is stale it ends its answer with the new file between
`<!-- handover-begin -->` and `<!-- handover-end -->`. This script takes the final result of the run (the `result` of the
last result message in the execution file), checks the text and writes it to OUTPUT. No block: nothing is written.

Usage: handover_text.py EXECUTION_FILE OUTPUT
Exit: 0 written, or no block in the answer; 2 the run result or the block is invalid (the step fails and says why).
"""
import json
import sys

import attribution  # tools/attribution.py: the one pattern list for tool and AI footers

BEGIN = "<!-- handover-begin -->"
END = "<!-- handover-end -->"
MAX_LINES = 60


def final_result(execution_text):
    """The `result` of the last result message of the execution file ("" when there is none)."""
    messages = json.loads(execution_text)
    if isinstance(messages, dict):
        messages = [messages]
    results = [m["result"] for m in messages
               if isinstance(m, dict) and m.get("type") == "result" and isinstance(m.get("result"), str)]
    return results[-1] if results else ""


def handover_block(result):
    """The text between the markers (ends with one newline), or None when the answer has no block."""
    if BEGIN not in result:
        return None
    body = result.split(BEGIN, 1)[1]
    if END not in body:
        raise ValueError("handover block has no end marker")
    return body.split(END, 1)[0].strip("\n") + "\n"


def check(block):
    """Raise ValueError unless the block is a plain HANDOVER.md of at most MAX_LINES lines without attribution."""
    if not block.strip():
        raise ValueError("handover block is empty")
    lines = block.count("\n")
    if lines > MAX_LINES:
        raise ValueError(f"handover has {lines} lines (max {MAX_LINES})")
    if attribution.found(block):
        raise ValueError("handover contains tool or AI attribution")


def main(argv):
    if len(argv) != 3:
        print("usage: handover_text.py EXECUTION_FILE OUTPUT", file=sys.stderr)
        return 2
    try:
        with open(argv[1], encoding="utf-8") as f:
            block = handover_block(final_result(f.read()))
    except (OSError, ValueError) as e:
        print(f"handover_text: cannot read the run result: {e}", file=sys.stderr)
        return 2
    if block is None:
        print("handover_text: no handover block in the run result: nothing written")
        return 0
    try:
        check(block)
    except ValueError as e:
        print(f"handover_text: {e}", file=sys.stderr)
        return 2
    with open(argv[2], "w", encoding="utf-8") as f:
        f.write(block)
    print(f"handover_text: wrote {argv[2]} ({block.count(chr(10))} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
