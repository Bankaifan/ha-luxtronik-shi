import json
import subprocess

import agent_guard
import pytest
import reapprove

REPO = "o/r"
OLD, NEW = "a" * 40, "b" * 40
BODY = "Adds app.\n\nCloses #1"
BHASH = agent_guard.body_hash(BODY)
ENV = {"GH_REPO": REPO, "APPROVER_BOT": "app/approver", "AUTHOR_BOT": "app/author", "OWNER": "Bankaifan"}


def patch(sha, lines="+print(1)\n", path="src/app.py", at=1):
    return (f"From {sha} Mon Sep 17 00:00:00 2001\nSubject: [PATCH] add\n\n---\n {path} | 1 +\n\n"
            f"diff --git a/{path} b/{path}\nindex 111..222 100644\n--- a/{path}\n+++ b/{path}\n@@ -{at},2 +{at},3 @@\n x = 0\n{lines} y = 1\n")


@pytest.fixture(autouse=True)
def _no_repo_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # CODEOWNERS and AGENTS.md of the real checkout must not leak into the tests


def pr_obj(**kw):
    d = {"state": "open", "commits": 1, "changed_files": 1, "body": BODY, "labels": [],
         "head": {"sha": NEW, "ref": "agent/1-x", "repo": {"full_name": REPO}}}
    d.update(kw)
    return d


def approval(sha=OLD, state="APPROVED", body=f"ok\n\nbody-hash: {BHASH}", login="app/approver", rid=7):
    return {"id": rid, "commit_id": sha, "state": state, "body": body, "user": {"login": login}}


def dismissal(prior="approved", message=None, actor="app/author", rid=7):
    d = {"review_id": rid, "dismissal_message": message, "previous_review_state": prior}
    return {"event": "review_dismissed", "actor": {"login": actor}, "dismissed_review": d}


class Gh:
    def __init__(self, pr=None, files=None, reviews=None, timeline=(), patches=None, moved_head=None, comments=()):
        self.comments = list(comments)
        self.pr = pr or pr_obj()
        self.files = files if files is not None else [{"filename": "src/app.py"}]
        self.reviews = reviews if reviews is not None else [approval()]
        self.timeline = list(timeline)
        self.patches = patches or {NEW: patch(NEW, at=9), OLD: patch(OLD)}
        self.moved_head, self.calls, self.pr_reads = moved_head, [], 0

    def __call__(self, *args):
        self.calls.append(args)
        path = args[-1] if "--slurp" in args else args[1] if args[0] == "api" else ""
        if "-X" in args:
            return ""
        if path.endswith("/files"):
            return json.dumps([self.files])
        if path.endswith("/reviews"):
            return json.dumps([self.reviews])
        if path.endswith("/comments"):
            return json.dumps([self.comments])
        if path.endswith("/timeline"):
            return json.dumps([self.timeline])
        if "/commits/" in path:
            return self.patches[path.rsplit("/", 1)[1]]
        self.pr_reads += 1
        if self.moved_head and self.pr_reads > 1:
            return json.dumps({**self.pr, "head": {**self.pr["head"], "sha": self.moved_head}})
        return json.dumps(self.pr)

    def posts(self):
        return [c for c in self.calls if "-X" in c]


def go(gh):
    try:
        return reapprove.run_reapprove("1", NEW, ENV, gh)
    except reapprove.Refuse as e:
        return str(e)


def test_same_patch_and_body_hash_approves_pinned_to_sha():
    gh = Gh()
    assert go(gh) == 0
    (post,) = gh.posts()
    assert post[:4] == ("api", "-X", "POST", f"repos/{REPO}/pulls/1/reviews")
    assert f"commit_id={NEW}" in post and "event=APPROVE" in post
    body = next(a for a in post if a.startswith("body="))
    assert f"body-hash: {BHASH}" in body and OLD in body and "without model" in body


def test_dismissed_push_time_approval_counts():
    gh = Gh(reviews=[approval(state="DISMISSED")], timeline=[dismissal()])
    assert go(gh) == 0


@pytest.mark.parametrize("bad", [
    dismissal(prior="changes_requested"), dismissal(prior=None), dismissal(message="revoked"),
    dismissal(actor="Bankaifan"), dismissal(rid=99),
])
def test_dismissed_review_refuses_unless_push_time_approval_is_proven(bad):
    assert "not a confirmed approval" in go(Gh(reviews=[approval(state="DISMISSED")], timeline=[bad]))


def test_dismissed_without_timeline_event_refuses():
    assert "not a confirmed approval" in go(Gh(reviews=[approval(state="DISMISSED")]))


def test_unreadable_previous_state_field_refuses():
    ev = dismissal()
    del ev["dismissed_review"]["previous_review_state"]
    assert "not a confirmed approval" in go(Gh(reviews=[approval(state="DISMISSED")], timeline=[ev]))


def test_changes_requested_review_refuses():
    gh = Gh(reviews=[approval(state="CHANGES_REQUESTED")])
    assert "not a confirmed approval" in go(gh) or "requested changes" in go(gh)


def test_other_reviewer_changes_requested_refuses():
    other = approval(sha=OLD, state="CHANGES_REQUESTED", login="Bankaifan", rid=8)
    assert "requested changes" in go(Gh(reviews=[approval(), other]))


def test_script_review_chains_from_newest_head():
    mid = "c" * 40
    gh = Gh(reviews=[approval(sha="d" * 40), approval(sha=mid)], patches={NEW: patch(NEW, at=9), mid: patch(mid)})
    assert go(gh) == 0
    assert "pulls/1/reviews" in gh.posts()[0][3] and f"since {mid}" in " ".join(gh.posts()[0])


def test_changed_patch_refuses():
    gh = Gh(patches={NEW: patch(NEW, lines="+print(2)\n"), OLD: patch(OLD)})
    assert "patch changed" in go(gh) and not gh.posts()


def test_edited_body_refuses():
    assert "body-hash" in go(Gh(pr=pr_obj(body="Other body")))


def test_review_without_body_hash_refuses():
    assert "body-hash" in go(Gh(reviews=[approval(body="ok")]))


def test_no_earlier_approval_refuses():
    assert "no earlier" in go(Gh(reviews=[approval(sha=NEW)]))
    assert "no earlier" in go(Gh(reviews=[approval(login="someone")]))


@pytest.mark.parametrize("kw", [
    {"commits": 2}, {"state": "closed"}, {"labels": [{"name": "needs-human"}]},
    {"head": {"sha": NEW, "ref": "feat/x", "repo": {"full_name": REPO}}},
    {"head": {"sha": NEW, "ref": "agent/1-x", "repo": {"full_name": "fork/r"}}},
    {"head": {"sha": "e" * 40, "ref": "agent/1-x", "repo": {"full_name": REPO}}},
])
def test_ineligible_pr_refuses(kw):
    gh = Gh(pr=pr_obj(**kw))
    assert isinstance(go(gh), str) and not gh.posts()


def test_design_pr_refuses():
    assert "design" in go(Gh(files=[{"filename": "docs/design/0009-x.md"}]))


def test_codeowners_path_refuses(tmp_path, monkeypatch):
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "CODEOWNERS").write_text("/src/ @Bankaifan\n")
    monkeypatch.chdir(tmp_path)
    assert "CODEOWNERS" in go(Gh())


def test_file_list_cap_and_mismatch_refuse():
    many = [{"filename": f"src/f{i}.py"} for i in range(100)]
    assert "capped" in go(Gh(pr=pr_obj(changed_files=100), files=many))
    assert "capped" in go(Gh(pr=pr_obj(changed_files=2)))


@pytest.mark.parametrize("path", ["tools/x.py", ".github/workflows/a.yml", ".agents/roles/x.md"])
def test_infra_class_refuses(path):
    gh = Gh(files=[{"filename": path}], patches={NEW: patch(NEW, path=path, at=9), OLD: patch(OLD, path=path)})
    assert "risk class" in go(gh) and not gh.posts()


def sec_gh(comments=(), labels=(), lines="+permissions: write\n"):
    path = "tools/x.py"
    return Gh(pr=pr_obj(labels=[{"name": n} for n in labels]), files=[{"filename": path}], comments=comments,
              patches={NEW: patch(NEW, lines=lines, path=path, at=9), OLD: patch(OLD, lines=lines, path=path)})


def verdict(kind="approve", sha=NEW, login="app/approver"):
    return {"user": {"login": login}, "body": f"security-review: {kind} {sha[:12]}"}


def test_security_patch_with_verdict_for_new_head_approves():
    gh = sec_gh(comments=[verdict()], labels=["risk:security"])
    assert go(gh) == 0 and len(gh.posts()) == 1


@pytest.mark.parametrize("comments", [
    [], [verdict(sha=OLD)], [verdict("changes")], [verdict(login="someone")], [verdict(), verdict("changes")],
])
def test_security_patch_without_confirmed_verdict_refuses(comments):
    gh = sec_gh(comments=comments, labels=["risk:security"])
    assert "no security-review approve" in go(gh) and not gh.posts()


def test_security_label_alone_needs_verdict():
    labels = pr_obj(labels=[{"name": "risk:security"}])
    assert "no security-review approve" in go(Gh(pr=labels))
    assert go(Gh(pr=labels, comments=[verdict()])) == 0


def test_security_patch_changed_still_refuses():
    gh = sec_gh(comments=[verdict()], labels=["risk:security"])
    gh.patches[NEW] = patch(NEW, lines="+permissions: admin\n", path="tools/x.py", at=9)
    assert "patch changed" in go(gh) and not gh.posts()


def test_security_codeowners_path_refuses(tmp_path, monkeypatch):
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "CODEOWNERS").write_text("/tools/x.py @Bankaifan\n")
    monkeypatch.chdir(tmp_path)
    assert "CODEOWNERS" in go(sec_gh(comments=[verdict()], labels=["risk:security"]))


@pytest.mark.parametrize("extra", ["GIT binary patch\nliteral 3\n", "Binary files a/x and b/x differ\n",
                                   "old mode 100644\nnew mode 100755\n", "diff --git a/z b/z\n", "A" * 300_001])
def test_truncated_binary_or_mode_patch_refuses(extra):
    assert "patch" in go(Gh(patches={NEW: patch(NEW, at=9) + extra, OLD: patch(OLD)}))


def test_head_moved_before_posting_refuses():
    gh = Gh(moved_head="f" * 40)
    assert "not open at this head" in go(gh) and not gh.posts()


def test_any_error_exits_1(monkeypatch):
    def boom(*a, **k):
        raise subprocess.CalledProcessError(1, "gh")
    monkeypatch.setattr(reapprove, "run_reapprove", boom)
    assert reapprove.main(["reapprove.py", "1", NEW]) == 1


def test_usage_error():
    assert reapprove.main(["reapprove.py", "x", "short"]) == 2


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), "-c", "user.email=a@b", "-c", "user.name=a", *args], check=True, capture_output=True)


def format_patch(cwd, rev):
    return subprocess.run(["git", "-C", str(cwd), "format-patch", "-1", "--stdout", rev], check=True,
                          capture_output=True, text=True).stdout


def test_patch_id_verbatim_on_mode_only_changes(tmp_path):
    """Measured: what git patch-id --verbatim does with mode-only commits (why check_patch refuses `old mode` lines)."""
    git(tmp_path, "init", "-q")
    (tmp_path / "f").write_text("x\n")
    (tmp_path / "g").write_text("y\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    (tmp_path / "f").chmod(0o755)
    git(tmp_path, "commit", "-qam", "mode f")
    (tmp_path / "g").chmod(0o755)
    git(tmp_path, "commit", "-qam", "mode g")
    mode_f, mode_g = format_patch(tmp_path, "HEAD~1"), format_patch(tmp_path, "HEAD")
    assert "old mode 100644" in mode_f
    ids = [subprocess.run(["git", "patch-id", "--verbatim"], input=p, capture_output=True, text=True,
                          check=True).stdout.split()
           for p in (mode_f, mode_g)]
    print("mode-only patch-ids:", ids)
    # Measured: git sees a mode-only change (an id is printed, and it differs per file). The script still refuses
    # `old mode` / `new mode` lines, so it never depends on that.
    assert all(len(i) == 2 for i in ids) and ids[0][0] != ids[1][0]
    for p in (mode_f, mode_g):
        with pytest.raises(reapprove.Refuse):
            reapprove.check_patch(p, 1)
