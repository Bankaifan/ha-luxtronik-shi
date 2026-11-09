#!/usr/bin/env bash
# Run every tools/gen_*.py, then fail if the generators changed or added files.
# Ok when the project has no generators.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
shopt -s nullglob
gens=(tools/gen_*.py)
if [ ${#gens[@]} -eq 0 ]; then
  echo "check_drift: no generators, ok"
  exit 0
fi
for g in "${gens[@]}"; do
  echo "check_drift: running $g"
  python3 "$g"
done
if ! git diff --exit-code || [ -n "$(git ls-files --others --exclude-standard)" ]; then
  echo "check_drift: generated files are out of date, run the generators and commit" >&2
  exit 1
fi
echo "check_drift: ok"
