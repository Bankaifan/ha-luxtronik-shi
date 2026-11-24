import json
import subprocess

import pr_title

ISSUE = "V0-WEATHER-SKY: weather in the world matches the display, plus a day clock"


def pr(title, head="agent/288-weather-forecast", cross=False):
    return {"number": 382, "title": title, "headRefName": head, "isCrossRepository": cross}


class Gh:
    def __init__(self, issue_title=ISSUE, fail=False):
        self.issue_title, self.fail, self.calls = issue_title, fail, []

    def __call__(self, *args):
        self.calls.append(args)
        if self.fail:
            raise subprocess.CalledProcessError(1, "gh")
        return json.dumps({"title": self.issue_title})


def test_the_title_gets_the_task_id_of_its_issue_and_keeps_its_own_summary():
    """roblox_energy PR 382: titled V0-WEATHER-FORECAST on the branch of issue 288 (V0-WEATHER-SKY)."""
    assert pr_title.fixed("V0-WEATHER-FORECAST: forecast arrow beside the clock", ISSUE) == (
        "V0-WEATHER-SKY: forecast arrow beside the clock")
    assert pr_title.fixed("forecast arrow", ISSUE) == "V0-WEATHER-SKY: forecast arrow"
    assert pr_title.fixed("V0-WEATHER-SKY: forecast arrow", ISSUE) is None
    assert pr_title.fixed("Add x", "Template sync 81292f7") is None and pr_title.fixed("Add x", None) is None
    long = pr_title.fixed("OTHER: " + "x" * 200, ISSUE)
    assert len(long) == 100 and long.startswith("V0-WEATHER-SKY: xxx")
    assert pr_title.fixed("OTHER: ", ISSUE) == "V0-WEATHER-SKY: update"


def test_fix_edits_only_a_same_repo_agent_issue_branch():
    run = Gh()
    assert pr_title.fix(pr("V0-WEATHER-FORECAST: forecast arrow"), run) == "V0-WEATHER-SKY: forecast arrow"
    assert run.calls == [("issue", "view", "288", "--json", "title"),
                         ("pr", "edit", "382", "--title", "V0-WEATHER-SKY: forecast arrow")]
    for other in (pr("X: y", head="agent/batch"), pr("X: y", head="template-sync/1.2"), pr("X: y", cross=True)):
        run = Gh()
        assert pr_title.fix(other, run) is None and run.calls == []
    run = Gh()
    assert pr_title.fix(pr("V0-WEATHER-SKY: fine"), run) is None and len(run.calls) == 1  # read, no edit
    assert pr_title.fix(pr("X: y"), Gh(fail=True)) is None  # a gh error changes nothing and raises nothing


def test_cli_never_fails_the_step(monkeypatch, capsys):
    def gone(*args):
        raise subprocess.CalledProcessError(1, "gh")

    monkeypatch.setattr(pr_title, "gh", gone)
    assert pr_title.main(["pr_title.py", "fix", "382"]) == 0 and capsys.readouterr().out.strip() == "ok"
    assert pr_title.main(["pr_title.py", "fix", "abc"]) == 2
