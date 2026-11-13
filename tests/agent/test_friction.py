import json
import subprocess

import friction


def body(*lines):
    return "Closes #1\n\n## Friction\n" + "\n".join(lines) + "\n"


def test_section_parsed():
    text = "why\n\n## Friction\n- slow lint step\n* unclear rule X.\n\n## Notes\n- not friction\n"
    assert friction.parse_friction(text) == [("slow lint step", False), ("unclear rule X.", False)]


def test_none_and_missing_section_ignored():
    assert friction.parse_friction(body("none")) == []
    assert friction.parse_friction(body("- None")) == []
    assert friction.parse_friction("just a body") == []
    assert friction.parse_friction(None) == []


def test_template_marker():
    assert friction.parse_friction(body("- template: missing tool")) == [("missing tool", True)]


def test_item_in_one_pr_yields_nothing():
    assert friction.issues_to_create([body("- slow lint"), body("none")], []) == []
    assert friction.issues_to_create([body("- slow lint", "- slow lint")], []) == []


def test_item_in_two_prs_yields_one_issue():
    bodies = [body("- Slow lint step"), body("- slow  lint step."), body("- other")]
    assert friction.issues_to_create(bodies, []) == [
        {"title": "Friction: Slow lint step", "template_only": False, "count": 2}]


def test_template_only_needs_every_report_marked():
    assert friction.issues_to_create([body("- template: x"), body("- template: x")], [])[0]["template_only"] is True
    assert friction.issues_to_create([body("- template: x"), body("- x")], [])[0]["template_only"] is False


def test_existing_title_is_deduped():
    bodies = [body("- slow lint"), body("- slow lint")]
    assert friction.issues_to_create(bodies, ["friction: Slow lint"]) == []


def test_create_issues_routes_template_items():
    calls = []
    items = [{"title": "Friction: a", "template_only": False, "count": 2},
             {"title": "Friction: b", "template_only": True, "count": 3}]
    assert friction.create_issues(items, lambda *a: calls.append(a)) == ["Friction: a", "Friction: b"]
    assert "--repo" not in calls[0]
    assert calls[1][-2:] == ("--repo", friction.TEMPLATE_REPO)


def test_main_prints_issues(monkeypatch, capsys):
    def _run(cmd, **kw):
        out = [{"body": body("- slow lint")}, {"body": body("- slow lint")}] if cmd[1] == "pr" else [{"title": "x"}]
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(out), stderr="")

    monkeypatch.setattr(friction.subprocess, "run", _run)
    assert friction.main() == 0
    assert json.loads(capsys.readouterr().out)[0]["title"] == "Friction: slow lint"
