"""Failure watch module (design 0008, sections 4.1-4.5), driven by a stateful fake gh."""
import datetime
import json

import failure_watch as fw
import guard_mark

KEY = "k" * 32
NOW = datetime.datetime(2026, 11, 10, 12, 0, tzinfo=datetime.UTC)
SINCE = NOW - datetime.timedelta(hours=1)


def mkrun(rid, wf="ci.yml", conclusion="failure", branch="main", fork=False):
    return {"id": rid, "path": f".github/workflows/{wf}", "conclusion": conclusion, "head_branch": branch,
            "html_url": f"https://github.com/o/r/actions/runs/{rid}", "created_at": "2026-11-10T11:30:00+00:00",
            "head_repository": {"fork": fork}}


def mkjobs(job="build", step="test", conclusion="failure"):
    return {"jobs": [{"name": job, "conclusion": conclusion,
                      "steps": [{"name": step, "conclusion": conclusion}] if step else []}]}


class Fake:
    def __init__(self):
        self.runs, self.jobs, self.issues, self.comments, self.calls = [], {}, {}, {}, []
        self.listed, self.timeline, self.pulls = {}, [], []

    def add_issue(self, title, body, state="OPEN", labels=()):
        n = len(self.issues) + 1
        self.issues[n] = {"number": n, "title": title, "state": state, "body": guard_mark.sign(title, body, KEY),
                          "labels": [{"name": x} for x in labels]}
        return n

    def __call__(self, *a):
        self.calls.append(a)
        if a[0] == "api":
            return self.api(a[1])
        if a[:2] == ("run", "list"):
            return json.dumps(self.listed.get(a[3], []))
        if a[0] == "label":
            return ""
        if a[:2] == ("issue", "list"):
            want = a[3]
            return json.dumps([i for i in self.issues.values() if want == "all" or i["state"] == "OPEN"])
        if a[:2] == ("issue", "create"):
            n = len(self.issues) + 1
            self.issues[n] = {"number": n, "title": a[3], "state": "OPEN", "body": a[a.index("--body") + 1],
                              "labels": [{"name": a[a.index("--label") + 1]}]}
            return f"https://github.com/o/r/issues/{n}\n"
        n = int(a[2])
        i = self.issues[n]
        if a[:2] == ("issue", "view"):
            return json.dumps({"body": i["body"], "comments": self.comments.get(n, [])})
        if a[:2] == ("issue", "comment"):
            self.comments.setdefault(n, []).append({"body": a[4]})
        elif a[:2] == ("issue", "edit"):
            self.edit(i, a)
        elif a[:2] == ("issue", "close"):
            i["state"] = "CLOSED"
        elif a[:2] == ("issue", "reopen"):
            i["state"] = "OPEN"
        return ""

    def edit(self, i, a):
        if "--body" in a:
            i["body"] = a[a.index("--body") + 1]
        if "--add-label" in a:
            i["labels"].append({"name": a[a.index("--add-label") + 1]})
        if "--remove-label" in a:
            i["labels"] = [x for x in i["labels"] if x["name"] != a[a.index("--remove-label") + 1]]

    def api(self, path):
        if "/jobs" in path:
            return json.dumps(self.jobs[int(path.split("/runs/")[1].split("/")[0])])
        if "/timeline" in path:
            return json.dumps(self.timeline)
        if "/pulls" in path:
            return json.dumps(self.pulls)
        return json.dumps({"workflow_runs": self.runs})

    def creates(self):
        return [a for a in self.calls if a[:2] == ("issue", "create")]

    def labels(self, n):
        return {x["name"] for x in self.issues[n]["labels"]}


def tick(fake, overdue=(), now=NOW):
    return fw.watch(SINCE, now, list(overdue), KEY, fake)


def failing(fake, rid, wf="ci.yml", job="build", step="test", branch="main"):
    fake.runs.append(mkrun(rid, wf, branch=branch))
    fake.jobs[rid] = mkjobs(job, step)


def title(sig="ci.yml / build / test"):
    return fw.TITLE_PREFIX + sig


def body(failures=1, rid=1, reopened=0, closed="none"):
    return fw.make_body("ci.yml / build / test", failures, f"https://github.com/o/r/actions/runs/{rid}", closed, reopened)


# --- collect -------------------------------------------------------------------------------------

def test_collect_keeps_real_failures_and_drops_the_rest():
    f = Fake()
    f.runs = [mkrun(1, conclusion="failure"), mkrun(2, conclusion="timed_out"), mkrun(3, conclusion="startup_failure"),
              mkrun(4, conclusion="cancelled"), mkrun(5, conclusion="skipped"), mkrun(6, conclusion="success"),
              mkrun(7, wf="validate.yml", branch="agent/9-x"), mkrun(8, wf="agent-review.yml", branch="agent/9-x"),
              mkrun(9, wf="status.yml"), mkrun(10, fork=True), mkrun(11, wf="validate.yml", branch="main")]
    assert [r["id"] for r in fw.collect(SINCE, NOW, f)] == [1, 2, 3, 11]


def test_collect_looks_back_at_most_24_hours_and_overlaps_five_minutes():
    f = Fake()
    fw.collect(NOW - datetime.timedelta(days=5), NOW, f)
    fw.collect(SINCE, NOW, f)
    paths = [c[1] for c in f.calls]
    assert "created=%3E%3D2026-11-09T12:00:00Z" in paths[0]
    assert "created=%3E%3D2026-11-10T10:55:00Z" in paths[1]


# --- signature -------------------------------------------------------------------------------------

def test_signature_sanitises_cuts_and_defaults_missing_step():
    f = Fake()
    f.jobs[1] = mkjobs("deploy", "Run `rm -rf /` <script>" + "x" * 80)
    sig = fw.signature(mkrun(1), f)
    wf, job, step = sig.split(" / ")
    assert wf == "ci.yml" and job == "deploy"
    assert len(step) == 60 and "`" not in step and "<" not in step
    f.jobs[2] = mkjobs("runner", None)
    assert fw.signature(mkrun(2), f).endswith(" / runner / -")


def test_hostile_step_name_cannot_inject_into_title_or_body():
    f = Fake()
    failing(f, 1, step="x\n@admin ![img](http://evil)")
    tick(f)
    issue = f.issues[1]
    text = issue["title"] + guard_mark.split(issue["body"])[0]
    assert "\n" not in issue["title"] and "@" not in text
    assert "[" not in text and "]" not in text and "`" not in text  # no markdown link, mention or code possible


# --- dedup, cap, priority --------------------------------------------------------------------------

def test_new_failure_opens_one_signed_issue_and_second_failure_updates_it():
    f = Fake()
    failing(f, 1)
    actions, _ = tick(f)
    assert actions == ["opened failure issue #1"]
    issue = f.issues[1]
    assert issue["title"] == title() and guard_mark.verify(issue["title"], issue["body"], KEY)
    assert "Failures: 1" in issue["body"] and "prio:2" in f.labels(1)
    failing(f, 2)
    actions, _ = tick(f)
    assert actions == ["updated failure issue #1"] and len(f.creates()) == 1
    assert "Failures: 2" in f.issues[1]["body"] and guard_mark.verify(issue["title"], issue["body"], KEY)


def test_same_run_in_overlap_is_not_counted_twice():
    f = Fake()
    failing(f, 1)
    tick(f)
    assert tick(f)[0] == []
    assert "Failures: 1" in f.issues[1]["body"]


def test_no_key_does_nothing():
    f = Fake()
    failing(f, 1)
    assert fw.watch(SINCE, NOW, [], "", f) == ([], SINCE)
    assert f.calls == []


def test_flood_cap_opens_five_defers_the_rest_and_updates_are_free():
    f = Fake()
    f.add_issue(title("ci.yml / build / old"), fw.make_body("ci.yml / build / old", 1, "https://github.com/o/r/actions/runs/0"))
    for n in range(1, 8):
        failing(f, n, step=f"s{n}")
    f.runs[0]["created_at"] = "2026-11-10T11:40:00+00:00"
    failing(f, 8, step="old")
    f.runs[-1]["created_at"] = "2026-11-10T11:35:00+00:00"
    actions, since = tick(f)
    assert len(f.creates()) == 5
    assert "failure watch: 2 signatures deferred" in actions
    assert "updated failure issue #1" in actions
    assert since == datetime.datetime(2026, 11, 10, 11, 30, tzinfo=datetime.UTC)


def test_priority_prio1_on_third_failure_and_for_merge_gates():
    f = Fake()
    for rid in (1, 2, 3):
        failing(f, rid)
        tick(f)
    assert "prio:1" in f.labels(1) and "prio:2" not in f.labels(1)
    g = Fake()
    for n, wf in enumerate(("risk.yml", "agent-security-review.yml", "validate.yml"), 1):
        failing(g, n, wf=wf)
    tick(g)
    assert all("prio:1" in g.labels(n) for n in (1, 2, 3))
    h = Fake()
    failing(h, 1, wf="validate.yml", branch="feature")
    tick(h)
    assert "prio:2" in h.labels(1)


# --- auto-close ------------------------------------------------------------------------------------

def green(f, rid=50, branch="main", job="build", conclusion="success"):
    f.listed["ci.yml"] = [{"conclusion": "success", "url": f"https://github.com/o/r/actions/runs/{rid}",
                           "headBranch": branch, "databaseId": rid}]
    f.jobs[rid] = mkjobs(job, "test", conclusion)


def test_success_of_the_same_job_closes_the_issue():
    f = Fake()
    n = f.add_issue(title(), body())
    green(f)
    actions, _ = tick(f)
    assert actions == ["closed failure issue #1"] and f.issues[n]["state"] == "CLOSED"
    assert "succeeded." in f.comments[n][0]["body"]
    assert "Closed by: https://github.com/o/r/actions/runs/50" in f.issues[n]["body"]
    assert guard_mark.verify(f.issues[n]["title"], f.issues[n]["body"], KEY)


def test_success_without_the_job_or_older_or_on_other_branch_does_not_close():
    for kw in ({"job": "other"}, {"branch": "feature"}, {"rid": 0}):
        f = Fake()
        f.add_issue(title(), body(rid=1))
        green(f, **kw)
        assert tick(f)[0] == [] and f.issues[1]["state"] == "OPEN"


def test_overdue_issue_is_closed_when_not_overdue_and_kept_when_overdue():
    f = Fake()
    t = "Overdue scheduled run: scout"
    f.add_issue(t, "x")
    f.add_issue("Overdue scheduled run: rule keeper", "x")
    f.add_issue("Overdue scheduled run: weekly summary", "x")
    f.add_issue("Overdue scheduled run: orchestrator", "stranger")
    f.issues[4]["body"] = "stranger"  # unsigned: left alone
    actions, _ = tick(f, overdue=["rule keeper"])
    assert f.issues[1]["state"] == "CLOSED" and f.issues[3]["state"] == "CLOSED"
    assert f.issues[2]["state"] == "OPEN" and f.issues[4]["state"] == "OPEN"
    assert actions == ["closed overdue issue #1", "closed overdue issue #3"]


# --- reopen and escalation ---------------------------------------------------------------------------

def test_failure_after_close_reopens_with_counter_and_pr_link():
    f = Fake()
    f.add_issue(title(), body(failures=2, rid=1), state="CLOSED", labels=["prio:2"])
    f.timeline = [{"event": "closed", "commit_id": "abc"}]
    f.pulls = [{"html_url": "https://github.com/o/r/pull/9"}]
    failing(f, 2)
    actions, _ = tick(f)
    issue = f.issues[1]
    assert actions == ["reopened failure issue #1"] and issue["state"] == "OPEN"
    assert "Failures: 3" in issue["body"] and "Reopened: 1" in issue["body"]
    assert "Closed by: https://github.com/o/r/pull/9" in issue["body"]
    assert "Same failure again after the fix in https://github.com/o/r/pull/9" in f.comments[1][0]["body"]
    assert guard_mark.verify(issue["title"], issue["body"], KEY) and "needs-human" not in f.labels(1)


def test_third_recurrence_escalates_to_needs_human_once():
    f = Fake()
    f.add_issue(title(), body(failures=5, rid=1, reopened=2), state="CLOSED", labels=["prio:1"])
    failing(f, 2)
    tick(f)
    assert "needs-human" in f.labels(1) and "Reopened: 3" in f.issues[1]["body"]
    note = f.comments[1][-1]["body"]
    assert "<!-- decision: yes=restart-issue no=close-issue -->" in note
    failing(f, 3)
    tick(f)  # still open: only a counter bump, no second label and no second note
    assert [x["name"] for x in f.issues[1]["labels"]].count("needs-human") == 1
    assert len(f.comments[1]) == 2 and guard_mark.verify(f.issues[1]["title"], f.issues[1]["body"], KEY)


def test_unsigned_lookalike_issue_is_ignored_for_state():
    f = Fake()
    n = f.add_issue(title(), body())
    f.issues[n]["body"] = "Failures: 99"
    failing(f, 2)
    tick(f)
    assert len(f.creates()) == 1


def test_no_log_text_in_any_body():
    f = Fake()
    failing(f, 1)
    tick(f)
    core = guard_mark.split(f.issues[1]["body"])[0]
    assert core == fw.make_body("ci.yml / build / test", 1, "https://github.com/o/r/actions/runs/1")
