import subprocess

import branch_repair


def g(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, env=branch_repair.git_env(), check=True, capture_output=True,
                          text=True).stdout.strip()


def commit(work, path, text, subject):
    (work / path).write_text(text)
    g(work, "add", "-A")
    g(work, "commit", "-q", "-m", subject)


def repo(tmp_path, version="0.14"):
    """A bare origin with main at `version`; returns (origin, work clone on main)."""
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    g(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    g(tmp_path, "clone", "-q", str(origin), str(work))
    g(work, "checkout", "-q", "-b", "main")
    commit(work, "VERSION", f"{version}\n", "base")
    g(work, "push", "-q", "origin", "main")
    return origin, work


def branch(work, name, *subjects):
    g(work, "checkout", "-q", "-b", name, "main")
    for n, subject in enumerate(subjects):
        commit(work, f"{name.replace('/', '-')}-{n}.txt", "x\n", subject)
    g(work, "push", "-q", "origin", name)
    return g(work, "rev-parse", "HEAD")


def release(work, version):
    """What the merged release PR does to main."""
    g(work, "checkout", "-q", "main")
    old = (work / "VERSION").read_text().strip()
    commit(work, "VERSION", f"{version}\n", f"V{old}-RELEASE: version {version}")
    g(work, "push", "-q", "origin", "main")


def subjects(origin, name):
    return g(origin, "log", "--format=%s", f"main..{name}").split("\n")


def test_a_release_on_main_gives_the_branch_the_new_version_in_every_subject(tmp_path):
    origin, work = repo(tmp_path)
    head = branch(work, "agent/341-neon-off", "V0.14-NEON-OFF: glow off", "V0.14-NEON-OFF: changelog fragment")
    tree = g(origin, "rev-parse", "agent/341-neon-off^{tree}")
    release(work, "0.15")
    assert branch_repair.repair(str(origin), "agent/341-neon-off", head, "NEON-OFF") == "pushed"
    assert subjects(origin, "agent/341-neon-off") == ["V0.15-NEON-OFF: changelog fragment", "V0.15-NEON-OFF: glow off"]
    assert g(origin, "merge-base", "--is-ancestor", "main", "agent/341-neon-off") == ""  # on top of main
    assert g(origin, "diff", "--name-only", "main", "agent/341-neon-off").split() == [
        "agent-341-neon-off-0.txt", "agent-341-neon-off-1.txt"]
    assert g(origin, "rev-parse", "agent/341-neon-off^{tree}") != tree  # main's VERSION is in it now
    new = g(origin, "rev-parse", "agent/341-neon-off")
    assert branch_repair.repair(str(origin), "agent/341-neon-off", new, "NEON-OFF") == "same"  # no second push
    assert g(origin, "rev-parse", "agent/341-neon-off") == new


def test_a_merge_of_main_disappears_and_wrong_subjects_are_set(tmp_path):
    origin, work = repo(tmp_path)
    branch(work, "agent/349-reset", "V0.14-SPARK-RESET-3: land reset", "tests for the land reset")
    release(work, "0.15")
    g(work, "checkout", "-q", "agent/349-reset")
    g(work, "merge", "-q", "--no-ff", "-m", "Merge branch 'main' into agent/349-reset", "main")
    g(work, "push", "-q", "origin", "agent/349-reset")
    head = g(work, "rev-parse", "HEAD")
    assert g(origin, "rev-list", "--merges", "--count", "main..agent/349-reset") == "1"
    assert branch_repair.repair(str(origin), "agent/349-reset", head, "SPARK-RESET-3") == "pushed"
    assert g(origin, "rev-list", "--merges", "--count", "main..agent/349-reset") == "0"
    assert subjects(origin, "agent/349-reset") == ["V0.15-SPARK-RESET-3: tests for the land reset",
                                                   "V0.15-SPARK-RESET-3: land reset"]


def test_nothing_is_pushed_for_a_moved_head_a_conflict_or_another_branch(tmp_path):
    origin, work = repo(tmp_path)
    head = branch(work, "agent/1-x", "V0.14-X: edit")
    g(work, "checkout", "-q", "-b", "agent/2-clash", "main")
    commit(work, "VERSION", "9.9\n", "V0.14-CLASH: edit the version")
    g(work, "push", "-q", "origin", "agent/2-clash")
    clash = g(work, "rev-parse", "HEAD")
    other = branch(work, "feature/y", "plain")
    release(work, "0.15")
    assert branch_repair.repair(str(origin), "agent/1-x", "0" * 40, "X") == "moved"
    assert branch_repair.repair(str(origin), "agent/2-clash", clash, "CLASH") == "conflict"
    assert branch_repair.repair(str(origin), "feature/y", other, "Y") is None
    assert branch_repair.repair(str(tmp_path / "missing.git"), "agent/1-x", head, "X") is None
    assert (g(origin, "rev-parse", "agent/1-x"), g(origin, "rev-parse", "agent/2-clash"),
            g(origin, "rev-parse", "feature/y")) == (head, clash, other)


def test_a_branch_main_already_holds_is_left_alone_and_no_name_keeps_the_subjects(tmp_path):
    origin, work = repo(tmp_path)
    head = branch(work, "agent/3-done", "V0.14-DONE: change")
    g(work, "checkout", "-q", "main")
    g(work, "cherry-pick", head)  # what a rebase merge does: the same patch, a new commit on main
    g(work, "push", "-q", "origin", "main")
    assert branch_repair.repair(str(origin), "agent/3-done", head, "DONE") == "empty"
    keep = branch(work, "agent/4-keep", "free text")
    release(work, "0.15")
    assert branch_repair.repair(str(origin), "agent/4-keep", keep, None) == "pushed"
    assert subjects(origin, "agent/4-keep") == ["free text"]


def test_the_token_goes_through_the_environment_only():
    env = branch_repair.git_env("s3cret")
    assert env["GIT_CONFIG_KEY_0"] == "http.extraheader"
    assert "s3cret" not in "".join(v for k, v in env.items() if k != "GIT_CONFIG_VALUE_0")
