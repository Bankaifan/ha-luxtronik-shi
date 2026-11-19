"""Give every commit of the branch the subject prefix `V<VERSION>-<NAME>: ` (docs/decisions/0017-hpo-flow.md). No model.

  python3 tools/commit_names.py NAME [BASE]     rewrite the subjects of BASE..HEAD (BASE default: origin/main)

VERSION is the VERSION file on BASE (`0.0` when there is none). A subject that already starts with a `V...-<NAME>: `
prefix of any version or name gets it replaced, any other subject gets the prefix in front. Authors, dates and trees
stay; only messages change, so the branch then needs `git push --force-with-lease`. `check_pr_form` names this command
when a subject is wrong: a wrong subject cannot be repaired by adding commits.
"""
import os
import re
import shlex
import subprocess
import sys

NAME = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+){0,2}")
_PREFIX = re.compile(rf"^V\d+(?:\.\d+)*-{NAME.pattern}:\s*")


def renamed(message, version, name):
    """MESSAGE with the subject prefix `V<version>-<name>: `; the body is untouched."""
    subject, sep, body = message.partition("\n")
    return f"V{version}-{name}: {_PREFIX.sub('', subject)}{sep}{body}"


def main(argv):
    if len(argv) == 4 and argv[1] == "--filter":  # git filter-branch --msg-filter: message on stdin
        sys.stdout.write(renamed(sys.stdin.read(), argv[2], argv[3]))
        return 0
    if len(argv) not in (2, 3) or not NAME.fullmatch(argv[1]) or argv[-1].startswith("-"):
        print(__doc__, file=sys.stderr)
        return 2
    name, base = argv[1], argv[2] if len(argv) == 3 else "origin/main"
    shown = subprocess.run(["git", "show", f"{base}:VERSION"], capture_output=True, text=True, check=False)
    version = shown.stdout.strip() if shown.returncode == 0 else ""
    if not re.fullmatch(r"\d+(?:\.\d+)+", version):  # no VERSION file, or no dot: the form check wants `V<x.y>-`
        version = f"{version}.0" if version.isdigit() else "0.0"
    cmd = " ".join(shlex.quote(a) for a in (sys.executable, os.path.abspath(__file__), "--filter", version, name))
    done = subprocess.run(["git", "filter-branch", "-f", "--msg-filter", cmd, f"{base}..HEAD"], check=False,
                          env={**os.environ, "FILTER_BRANCH_SQUELCH_WARNING": "1"})
    return done.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv))
