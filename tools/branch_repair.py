"""Bring an agent branch up to date without a model: rebase it onto main, set its commit subjects, push it back.

The merge train (tools/train.py) calls `repair` for the PR it would otherwise update through the update-branch API,
and for an open agent PR whose commit subjects fail the form check (tools/task_ids.py). One call, in a scratch clone:
1. `git rebase origin/<base>`: the branch becomes a straight line on top of main. A merge of main into the branch
   (`Merge branch 'main' into agent/...`) disappears, and so does a commit main already holds.
2. `tools/commit_names.py NAME origin/<base>` (this checkout's copy): every commit gets `V<VERSION>-<NAME>: ` with the
   VERSION of main, so a release that landed meanwhile shows in the subjects.
3. `git push --force-with-lease=<branch>:<head>`: only when the branch still is the head the caller saw.
Returns "pushed", "same" (already a straight line on main with the right subjects), "moved" (the branch is no longer
at `head`), "conflict" (the rebase stops: the conflict fix round owns that), "empty" (main holds every commit) or
None (git error, push refused). Nothing is pushed in any case but "pushed". Only branches under `agent/` are touched.
"""
import base64
import os
import subprocess
import sys
import tempfile
from pathlib import Path

NAMES = Path(__file__).resolve().parent / "commit_names.py"  # always this checkout's copy (main), never the branch's
COMMITTER = ("Daniel", "476059+Bankaifan@users.noreply.github.com")


def git_env(token=""):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_COMMITTER_NAME": COMMITTER[0],
           "GIT_COMMITTER_EMAIL": COMMITTER[1], "GIT_AUTHOR_NAME": COMMITTER[0], "GIT_AUTHOR_EMAIL": COMMITTER[1]}
    if token:  # through the environment, never argv
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.extraheader",
                   GIT_CONFIG_VALUE_0=f"AUTHORIZATION: basic {basic}")
    return env


def repair(remote, branch, head, name, token="", base="main"):
    """See the module text. `name` None: rebase only, the subjects stay."""
    if not branch.startswith("agent/"):
        return None
    env = git_env(token)

    def git(tmp, *args, check=True):
        return subprocess.run(["git", *args], cwd=tmp, env=env, check=check, capture_output=True, text=True)

    try:
        with tempfile.TemporaryDirectory() as tmp:
            git(tmp, "init", "-q")
            git(tmp, "fetch", "-q", remote, f"+refs/heads/{base}:refs/remotes/origin/{base}",
                f"+refs/heads/{branch}:refs/remotes/origin/{branch}")
            if git(tmp, "rev-parse", f"origin/{branch}").stdout.strip() != head:
                return "moved"
            git(tmp, "checkout", "-q", "-b", "repair", f"origin/{branch}")
            if git(tmp, "rebase", f"origin/{base}", check=False).returncode != 0:
                return "conflict"
            if not git(tmp, "rev-list", f"origin/{base}..HEAD").stdout.strip():
                return "empty"
            if name:
                done = subprocess.run([sys.executable, "-I", str(NAMES), name, f"origin/{base}"], cwd=tmp, check=False,
                                      env=env, capture_output=True, text=True)
                if done.returncode != 0:
                    return None
            if git(tmp, "rev-parse", "HEAD").stdout.strip() == head:
                return "same"
            git(tmp, "push", "-q", f"--force-with-lease=refs/heads/{branch}:{head}", remote, f"HEAD:refs/heads/{branch}")
            return "pushed"
    except (subprocess.CalledProcessError, OSError):
        return None
