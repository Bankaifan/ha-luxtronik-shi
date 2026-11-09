"""Check that a missing optional repo variable cannot silently switch a workflow job off.

A repo variable that is not set reads as null in a GitHub expression. Null compared with the string '0'
counts as 0, so `vars.X != '0'` is false when X is unset and the job is skipped. Every `vars.NAME != 'literal'`
(or `'literal' != vars.NAME`) in .github/workflows/*.yml must therefore have an explicit empty-string case on the
same line (`vars.NAME == ''`), or compute the effective value first, e.g. `(vars.NAME || '3') != '0'` (that form
never matches this check).

Usage: python3 tools/check/check_var_defaults.py [workflow-dir]
"""
import pathlib
import re
import sys

NOT_EQUAL = re.compile(r"""vars\.(\w+)\s*!=\s*'[^']*'|'[^']*'\s*!=\s*vars\.(\w+)""")


def findings(text):
    """(line number, variable name, line) for each unguarded `!=` comparison on a variable."""
    out = []
    for no, line in enumerate(text.splitlines(), 1):
        for m in NOT_EQUAL.finditer(line):
            name = m.group(1) or m.group(2)
            if not re.search(rf"vars\.{name}\s*==\s*''", line):
                out.append((no, name, line.strip()))
    return out


def main(argv) -> int:
    root = pathlib.Path(argv[1]) if len(argv) > 1 else pathlib.Path(__file__).resolve().parents[2] / ".github/workflows"
    errors = []
    for path in sorted(root.glob("*.yml")):
        for no, name, src in findings(path.read_text(encoding="utf-8")):
            errors.append(f"{path}:{no}: vars.{name} with != and no empty-string case (unset means skipped): {src}")
    for e in errors:
        print(f"check_var_defaults: {e}")
    if not errors:
        print("check_var_defaults: ok")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
