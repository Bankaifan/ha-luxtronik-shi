import json
import subprocess

import landed


def merged(n, head, body, **kw):
    return {"number": n, "headRefName": head, "body": body, "baseRefName": "main", "isCrossRepository": False,
            "mergedAt": "2026-11-22T01:00:00Z", **kw}


def issue(n, *labels, reason=None):
    return {"number": n, "labels": [{"name": x} for x in labels], "stateReason": reason}


class Gh:
    def __init__(self, prs, issues, fail=()):
        self.prs, self.issues, self.fail, self.calls = prs, issues, fail, []

    def __call__(self, *args):
        if args[:2] == ("pr", "list"):
            return json.dumps(self.prs)
        if args[:2] == ("issue", "list"):
            return json.dumps(self.issues)
        if args[2] in self.fail:
            raise subprocess.CalledProcessError(1, "gh")
        self.calls.append(args)
        return ""


def test_issues_of_a_merged_pr_are_its_closing_keywords_and_its_branch_unless_refs():
    assert landed.issues_of(merged(9, "agent/316-x", "Adds x. #316")) == [316]
    assert landed.issues_of(merged(9, "agent/316-x", "Closes #316, fixes o/r#7 and resolves #12")) == [316, 12]
    assert landed.issues_of(merged(9, "agent/316-x", "Part 1.\nRefs #316")) == []
    assert landed.issues_of(merged(9, "agent/316-x", "Closes #316\nRefs #316, Refs #400")) == [316]
    assert landed.issues_of(merged(9, "agent/batch", "Batch: #1@abcdef0 #2@abcdef1\nCloses #311\nRefs #313")) == [311]
    assert landed.issues_of(merged(9, "feature/x", None)) == []


def test_only_open_not_reopened_issues_of_merged_same_repo_agent_prs_into_main_are_closed():
    prs = [merged(20, "agent/316-x", "work on #316"), merged(21, "agent/313-y", "Closes #313"),
           merged(22, "agent/311-z", "Refs #311"), merged(23, "agent/317-r", "#317"),
           merged(24, "agent/323-fork", "#323", isCrossRepository=True), merged(25, "agent/324-b", "#324", baseRefName="dev"),
           merged(26, "hand/325", "Closes #325"), merged(27, "agent/316-again", "Closes #316")]
    issues = [issue(316, "agent:dev", "prio:1"), issue(311), issue(317, reason="REOPENED"), issue(323), issue(324), issue(325)]
    assert landed.landed(prs, issues) == [(316, 20)]
    run = Gh(prs, issues)
    assert landed.close_landed(run) == ["closed issue #316: PR #20 is merged"]
    assert run.calls == [("issue", "close", "316", "--reason", "completed", "--comment", "Completed by #20 (merged)."),
                         ("issue", "edit", "316", "--remove-label", "agent:dev")]


def test_one_failing_close_does_not_stop_the_others_and_nothing_merged_reads_no_issues():
    prs = [merged(20, "agent/1-x", "#1"), merged(21, "agent/2-y", "#2")]
    run = Gh(prs, [issue(1), issue(2)], fail=("1",))
    assert landed.close_landed(run) == ["closing issue #1 failed (CalledProcessError)", "closed issue #2: PR #21 is merged"]
    assert Gh([], [issue(1)]).calls == [] and landed.close_landed(Gh([], [issue(1)])) == []
