"""Ratchet for the line coverage of tools/ (issue #797).

A full test run (Makefile scope ALL) records coverage data; this check fails when the total is below the floor in
docs/coverage.json ({"floor": percent}). The floor is raised or lowered only by a deliberate edit of that file.
Skipped: a scoped run (`--scoped`, a partial run has no meaningful total), no tests/ or no floor file (downstream projects).
"""
import json
import math
import pathlib
import subprocess
import sys

FLOOR_FILE = "docs/coverage.json"


def load_floor(root):
    """The floor from docs/coverage.json, or None when the file is absent; ValueError when malformed."""
    path = root / FLOOR_FILE
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    floor = data.get("floor") if isinstance(data, dict) else None
    if isinstance(floor, bool) or not isinstance(floor, (int, float)) or not 0 <= floor <= 100:
        raise ValueError(f'{FLOOR_FILE}: expected {{"floor": percent between 0 and 100}}')
    return floor


def measure(root):
    """Total line coverage percent of the recorded data (`coverage json`)."""
    proc = subprocess.run(
        [sys.executable, "-m", "coverage", "json", "-o", "-"], cwd=root, capture_output=True, text=True, check=True
    )
    return float(json.loads(proc.stdout)["totals"]["percent_covered"])


def main(root=None, scoped=False) -> int:
    root = pathlib.Path(root) if root is not None else pathlib.Path(__file__).resolve().parent.parent.parent
    if scoped:
        print("check_coverage: skipped (scoped run, no meaningful total)")
        return 0
    if not (root / "tests").is_dir():
        print("check_coverage: skipped (no tests/)")
        return 0
    try:
        floor = load_floor(root)
    except (OSError, ValueError) as e:
        print(f"check_coverage: cannot run: {e}", file=sys.stderr)
        return 2
    if floor is None:
        print(f"check_coverage: skipped (no {FLOOR_FILE})")
        return 0
    try:
        total = measure(root)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as e:
        print(f"check_coverage: cannot run: {e}", file=sys.stderr)
        return 2
    if total < floor:
        print(f"check_coverage: coverage of tools/ is {total:.2f} %, below the floor of {floor} % in {FLOOR_FILE}")
        return 1
    print(f"check_coverage: ok ({math.floor(total * 100) / 100:.2f} % at or above the floor of {floor} %)")
    return 0


if __name__ == "__main__":
    sys.exit(main(scoped="--scoped" in sys.argv[1:]))
