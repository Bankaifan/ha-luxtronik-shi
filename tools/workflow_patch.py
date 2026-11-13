"""Carry agent workflow changes past the model token, which has no `workflows` scope (design 0017 step 3).

  workflow_patch.py stash PATTERN (agent-dev/agent-fix, after the model step) for each local branch matching PATTERN
                                  (agent/<issue>-*) that changes .github/workflows/: move those changes into
                                  .agents/workflow-patches/<issue>.patch,
                                  squash to one commit, push (no workflow file in the push). Prints each pushed branch.
  workflow_patch.py apply BRANCH SHA  (workflow-apply.yml, after a green security review of SHA) apply the patch files
                                  of BRANCH at SHA, drop them, squash, push. Refuses owner paths (CODEOWNERS) and any path
                                  outside .github/workflows/.
The security reviewer judges the patch file like any other diff; the applied head is reviewed again.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci.risk import SECURITY_FILES, parse_header

PATCH_DIR = ".agents/workflow-patches/"
WORKFLOWS = ".github/workflows/"


def git(*args, check=True):
    out = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args], check=check, capture_output=True, text=True)
    return out.stdout


def patch_paths(text):
    """Paths named in the `diff --git` lines of a patch."""
    out = []
    for line in text.splitlines():
        if line.startswith("diff --git "):
            out += [p for p in parse_header(line) if p]
    return out


# The gate itself and owner paths: a patch must not rewrite who reviews or merges it.
DENY = ("workflow-apply.yml", "agent-security-review.yml", "automerge.yml")
NAME = re.compile(r"^\.agents/workflow-patches/\d+(-\d+)?\.patch$")
META = re.compile(r"^(rename |copy |similarity |dissimilarity |GIT binary patch|Binary files |(old|new|new file|deleted file) mode (?!100644$))",
                  re.MULTILINE)


def path_refusal(p):
    if not p.startswith(WORKFLOWS) or ".." in p.split("/") or p.count("/") != 2:
        return f"{p} is outside {WORKFLOWS}"
    if any(p.startswith(s) for s in SECURITY_FILES) or p.removeprefix(WORKFLOWS) in DENY:
        return f"{p} is an owner or gate path: Daniel applies it"
    return None


def refusal(text):
    """Why a patch must not be applied by script, or None (the applied index is checked again)."""
    paths = patch_paths(text)
    if not paths:
        return "no file in the patch"
    m = META.search(text)
    if m:
        return f"unsupported patch line: {m.group(0).strip()}"
    return next((r for r in map(path_refusal, paths) if r), None)


def squash(base, message_from):
    """One commit on top of base with the index as tree, message and author of `message_from`."""
    git("reset", "-q", "--soft", base)
    git("commit", "-q", "--allow-empty", "-C", message_from)


def merge_base(ref, candidates):
    """First merge base of ref with one of the candidates; a shallow fetch can hide the newest main."""
    for c in candidates:
        if c:
            out = subprocess.run(["git", "merge-base", ref, c], capture_output=True, text=True, check=False)
            if out.returncode == 0:
                return out.stdout.strip()
    return None


def stash(pattern, remote="origin", main=None):
    main = main or os.environ.get("DEFAULT_BRANCH", "main")
    pushed = []
    refs = git("for-each-ref", "--format=%(refname:short)", f"refs/heads/{pattern}").split()
    for ref in refs:
        m = re.match(r"agent/(\d+)-", ref)
        base = merge_base(ref, [f"{remote}/{main}", os.environ.get("BASE_SHA")])
        if not m or not base:
            print(f"skipped {ref}: no issue number or no merge base", file=sys.stderr)
            continue
        issue = m.group(1)
        files = git("diff", "--no-renames", "--name-status", base, ref, "--", WORKFLOWS).splitlines()
        if not files:
            continue
        patch = git("diff", "--no-renames", base, ref, "--", WORKFLOWS)
        tip = git("rev-parse", ref).strip()
        git("checkout", "-q", "-f", ref)
        for line in files:
            status, path = line.split("\t", 1)
            if status == "A":
                git("rm", "-q", "-f", "--", path)
            else:
                git("checkout", base, "--", path)
        os.makedirs(PATCH_DIR, exist_ok=True)
        n = len([f for f in os.listdir(PATCH_DIR) if f.startswith((f"{issue}.", f"{issue}-"))])
        name = f"{PATCH_DIR}{issue}.patch" if not n else f"{PATCH_DIR}{issue}-{n}.patch"
        with open(name, "w", encoding="utf-8") as f:
            f.write(patch)
        git("add", name)
        squash(base, tip)
        git("push", "-q", f"--force-with-lease={ref}", remote, f"{ref}:{ref}")
        pushed.append(ref)
        print(ref)
    return pushed


def patch_order(path):
    m = re.search(r"(\d+)(?:-(\d+))?\.patch$", path)
    return int(m.group(1)), int(m.group(2) or 0)


def apply(branch, sha, remote="origin", main=None):
    """Exit code 0 applied or nothing to do, 3 refused (reason on stdout). Works on a private index, no checkout."""
    main = main or os.environ.get("DEFAULT_BRANCH", "main")
    git("fetch", "-q", remote, f"+refs/heads/{branch}:refs/remotes/{remote}/{branch}", f"+refs/heads/{main}:refs/remotes/{remote}/{main}")
    if git("rev-parse", f"{remote}/{branch}").strip() != sha:
        print(f"{branch} moved past {sha[:7]}: nothing applied")
        return 0
    base = git("merge-base", sha, f"{remote}/{main}").strip()
    names = [p for p in git("diff", "-z", "--name-only", "--no-renames", base, sha, "--", PATCH_DIR).split("\0") if p]
    if not names:
        print("no workflow patch")
        return 0
    env = dict(os.environ, GIT_INDEX_FILE=os.path.join(git("rev-parse", "--absolute-git-dir").strip(), "workflow-apply.index"))

    def run(*a, **k):
        return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *a], env=env, capture_output=True, text=True,
                              check=False, **k)

    run("read-tree", sha)
    for p in sorted(names, key=patch_order):
        mode = git("ls-tree", sha, "--", p).split(" ", 1)[0]
        if not NAME.match(p) or mode != "100644":
            print(f"refused {p}: not a plain patch file")
            return 3
        text = git("cat-file", "blob", f"{sha}:{p}")
        why = refusal(text)
        if why:
            print(f"refused {p}: {why}")
            return 3
        if run("apply", "--cached", "-", input=text).returncode:
            print(f"refused {p}: the patch does not apply")
            return 3
        run("rm", "-q", "--cached", "--", p)
    changed = [p for p in run("diff", "--cached", "-z", "--name-only", "--no-renames", sha).stdout.split("\0") if p]
    bad = [p for p in changed if not p.startswith(PATCH_DIR) and path_refusal(p)]
    if bad:
        print(f"refused: the patch reaches {', '.join(bad)}")
        return 3
    tree = run("write-tree").stdout.strip()
    who = git("log", "-1", "--format=%an%x00%ae%x00%aI", sha).strip().split("\0")
    msg = git("log", "-1", "--format=%B", sha)
    cenv = dict(os.environ, GIT_AUTHOR_NAME=who[0], GIT_AUTHOR_EMAIL=who[1], GIT_AUTHOR_DATE=who[2])
    new = subprocess.run(["git", "commit-tree", tree, "-p", base], input=msg, env=cenv, capture_output=True, text=True,
                         check=True).stdout.strip()
    git("push", "-q", f"--force-with-lease={branch}:{sha}", remote, f"{new}:refs/heads/{branch}")
    print(f"applied {', '.join(names)} on {branch}")
    return 0


def main(argv):
    if len(argv) == 2 and argv[0] == "stash":
        stash(argv[1])
        return 0
    if len(argv) == 3 and argv[0] == "apply":
        return apply(argv[1], argv[2])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
