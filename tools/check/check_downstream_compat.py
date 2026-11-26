"""Downstream sync compatibility (no model): fail a change that a project on an older release cannot sync.

A project syncs a new template release with the tools of the release it is on: its template-sync workflow runs its
own (old) tools/template_sync.py on the new tools/ci/install_tools.sh and then installs the result with
`pip install --only-binary=:all:`. This check runs the parsers of the last RELEASES releases (the commits that changed
VERSION) on this tree's install_tools.sh, each in its own process with that release's tools/, and writes the
requirements for the workflow's install step. A token an older parser refuses fails here, before the release.

Runs only in the template (`.agents/managed.json` exists only there). Needs the full history (fetch-depth 0).
CLI: check_downstream_compat.py [--releases N] [--out requirements.txt]
"""
import argparse
import json
import pathlib
import subprocess
import sys
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SCRIPT = "tools/ci/install_tools.sh"
RELEASES = 5
_PARSE = (
    "import json, sys; sys.path.insert(0, sys.argv[1]); import template_sync as ts\n"
    "f = getattr(ts, 'tool_requirements', None)\n"
    "if f is None: print(json.dumps(None)); sys.exit(0)\n"
    "try: print(json.dumps(f(open(sys.argv[2], encoding='utf-8').read())))\n"
    "except ValueError as exc: print(json.dumps(str(exc)))\n"
)


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


def release_commits(root, count):
    """The newest `count` commits that changed VERSION, newest first."""
    return _git(root, "log", f"-n{count}", "--format=%H", "--", "VERSION").split()


def parse_with(root, sha, script_path):
    """The requirements the parser of release `sha` reads from script_path: a list, an error string, or None when
    that release has no tool_requirements (older than the tool pins, design 0016)."""
    with tempfile.TemporaryDirectory() as tmp:
        archive = subprocess.run(["git", "-C", str(root), "archive", "--format=tar", sha, "tools"],
                                 check=True, capture_output=True).stdout
        tar_path = pathlib.Path(tmp, "tools.tar")
        tar_path.write_bytes(archive)
        with tarfile.open(tar_path) as tar:
            tar.extractall(tmp, filter="data")
        res = subprocess.run([sys.executable, "-I", "-c", _PARSE, str(pathlib.Path(tmp, "tools")), str(script_path)],
                             capture_output=True, text=True, cwd=tmp, check=False)
    if res.returncode != 0:
        return f"parser crashed: {res.stderr.strip().splitlines()[-1] if res.stderr.strip() else res.returncode}"
    return json.loads(res.stdout)


def check(root, count):
    """(errors, requirements): one error line per release whose parser refuses this tree's script."""
    shas = release_commits(root, count)
    if not shas:
        return ["no release commits found (VERSION history): the job needs fetch-depth 0"], []
    script = pathlib.Path(root, SCRIPT)
    errors, reqs = [], None
    for sha in shas:
        got = parse_with(root, sha, script)
        if got is None:
            continue
        if isinstance(got, str):
            errors.append(f"projects on release {sha[:7]} cannot read {SCRIPT}: {got}")
        elif reqs is None:
            reqs = got
    if reqs is None and not errors:
        errors.append("no release in the window reads tool pins (tool_requirements): nothing was checked")
    return errors, reqs or []


def main(argv=None):
    ap = argparse.ArgumentParser(prog="check_downstream_compat.py")
    ap.add_argument("--releases", type=int, default=RELEASES)
    ap.add_argument("--out", help="write the requirements for the binary-only install check")
    args = ap.parse_args(argv)
    if not (ROOT / ".agents" / "managed.json").is_file():
        print("check_downstream_compat: not the template, skipped")
        return 0
    errors, reqs = check(ROOT, args.releases)
    for line in errors:
        print(f"check_downstream_compat: {line}", file=sys.stderr)
    if errors:
        return 1
    if args.out:
        pathlib.Path(args.out).write_text("".join(f"{r}\n" for r in reqs), encoding="utf-8")
    print(f"check_downstream_compat: ok, {len(reqs)} requirements readable by the last {args.releases} releases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
