import json
import subprocess

import review_delta

OLD, NEW = "a" * 40, "b" * 40
ENV = {"GH_REPO": "o/r", "APPROVER_BOT": "appr[bot]"}


def review(commit, state="CHANGES_REQUESTED", login="appr[bot]", body="fix x"):
    return {"commit_id": commit, "state": state, "user": {"login": login}, "body": body}


def fake(reviews, status="ahead", diff="diff --git a/x b/x\n+1\n", fail_compare=False):
    def run(*args):
        if "--paginate" in args:
            return json.dumps([reviews])
        if "-H" in args:
            if fail_compare:
                raise subprocess.CalledProcessError(1, "gh")
            return diff
        if fail_compare:
            raise subprocess.CalledProcessError(1, "gh")
        return json.dumps({"status": status})
    return run


def test_round_one_stages_nothing(tmp_path):
    assert review_delta.stage_delta(1, NEW, ENV, fake([]), str(tmp_path)) == "full"
    assert not list(tmp_path.iterdir())


def test_other_authors_reviews_do_not_count(tmp_path):
    run = fake([review(OLD, login="someone")])
    assert review_delta.stage_delta(1, NEW, ENV, run, str(tmp_path)) == "full"


def test_later_round_stages_delta_and_prior_findings(tmp_path):
    run = fake([review(OLD, body="fix x in a.py")])
    assert review_delta.stage_delta(1, NEW, ENV, run, str(tmp_path)) == "delta"
    assert "+1" in (tmp_path / "delta.diff").read_text()
    findings = (tmp_path / "prior-findings.md").read_text()
    assert "fix x in a.py" in findings and OLD[:12] in findings


def test_head_not_an_ancestor_falls_back_to_full_diff(tmp_path):
    for status in ("diverged", "behind", "identical"):
        run = fake([review(OLD)], status=status)
        assert review_delta.stage_delta(1, NEW, ENV, run, str(tmp_path)) == "full"
    assert not list(tmp_path.iterdir())


def test_compare_error_falls_back_to_full_diff(tmp_path):
    run = fake([review(OLD)], fail_compare=True)
    assert review_delta.stage_delta(1, NEW, ENV, run, str(tmp_path)) == "full"
    assert not list(tmp_path.iterdir())


def test_same_head_or_empty_delta_is_full(tmp_path):
    assert review_delta.stage_delta(1, NEW, ENV, fake([review(NEW)]), str(tmp_path)) == "full"
    assert review_delta.stage_delta(1, NEW, ENV, fake([review(OLD)], diff="\n"), str(tmp_path)) == "full"


def test_latest_approver_review_sets_the_base(tmp_path):
    mid = "c" * 40
    seen = []

    def run(*args):
        seen.append(args)
        return fake([review(OLD), review(mid, "APPROVED")])(*args)
    assert review_delta.stage_delta(1, NEW, ENV, run, str(tmp_path)) == "delta"
    assert any(f"compare/{mid}...{NEW}" in a for call in seen for a in call)


def test_main_rejects_bad_arguments():
    assert review_delta.main(["x", "1"]) == 2
    assert review_delta.main(["x", "abc", NEW]) == 2
