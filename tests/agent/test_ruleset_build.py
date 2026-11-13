"""Required checks: `tools/ruleset.py build` merges `.agents/checks.json` into the template ruleset (design 0016, 4.3)."""
import importlib.util
import json
import pathlib
import sys

import pytest

TOOLS = pathlib.Path(__file__).resolve().parent.parent.parent / "tools"
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "ci"))

import risk
import ruleset

TEMPLATE = {"validate", "agent-smoke", "risk", "security-review"}
RULESET = ROOT / ".github" / "rulesets" / "main.json"


def write_checks(tmp_path, data):
    path = tmp_path / "checks.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return str(path)


def built_contexts(checks_path):
    text = ruleset.build(str(RULESET), checks_path)
    rules = json.loads(text)["rules"]
    return {c["context"] for r in rules if r["type"] == "required_status_checks"
            for c in r["parameters"]["required_status_checks"]}


def test_build_adds_project_checks_to_template(tmp_path):
    checks = write_checks(tmp_path, {"required": ["lint-docs"]})
    assert built_contexts(checks) == TEMPLATE | {"lint-docs"}
    assert ruleset.contexts(str(RULESET), checks) == TEMPLATE | {"lint-docs"}


def test_build_without_checks_file_is_the_template(tmp_path):
    missing = str(tmp_path / "absent.json")
    assert built_contexts(missing) == TEMPLATE
    assert ruleset.contexts(str(RULESET), missing) == TEMPLATE


def test_build_keeps_the_rest_of_the_template(tmp_path):
    original = json.loads(RULESET.read_text(encoding="utf-8"))
    built = json.loads(ruleset.build(str(RULESET), write_checks(tmp_path, {"required": ["lint-docs"]})))
    assert [r["type"] for r in built["rules"]] == [r["type"] for r in original["rules"]]
    assert built["bypass_actors"] == original["bypass_actors"]
    strict = next(r for r in built["rules"] if r["type"] == "required_status_checks")
    assert strict["parameters"]["strict_required_status_checks_policy"] is True


@pytest.mark.parametrize("name", ["Lint", "lint docs", "lint_docs", "lint.docs", "-lint", "", "a" * 64, "x;rm"])
def test_malformed_names_are_refused(tmp_path, name):
    checks = write_checks(tmp_path, {"required": [name]})
    with pytest.raises(ValueError, match="malformed"):
        ruleset.build(str(RULESET), checks)


def test_name_at_the_length_limit_is_accepted(tmp_path):
    checks = write_checks(tmp_path, {"required": ["a" * 63]})
    assert ("a" * 63) in built_contexts(checks)


def test_non_string_name_is_refused(tmp_path):
    with pytest.raises(ValueError, match="malformed"):
        ruleset.build(str(RULESET), write_checks(tmp_path, {"required": [1]}))


def test_duplicate_names_are_refused(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        ruleset.build(str(RULESET), write_checks(tmp_path, {"required": ["lint-docs", "lint-docs"]}))


def test_name_of_a_template_check_is_refused(tmp_path):
    with pytest.raises(ValueError, match="repeats template checks"):
        ruleset.contexts(str(RULESET), write_checks(tmp_path, {"required": ["validate"]}))


@pytest.mark.parametrize("data", ["[]", '{"required": "lint-docs"}', '{"required": [], "extra": 1}',
                                  '{"names": []}', "{not json"])
def test_malformed_file_is_refused(tmp_path, data):
    with pytest.raises(ValueError):
        ruleset.build(str(RULESET), write_checks(tmp_path, data))


def test_cli_build_exit_codes(tmp_path, capsys):
    assert ruleset.main(["ruleset.py"]) == 2
    assert ruleset.main(["ruleset.py", "build"]) == 0  # the real repo: no checks.json, so the template
    out = json.loads(capsys.readouterr().out)
    assert TEMPLATE <= {c["context"] for r in out["rules"] if r["type"] == "required_status_checks"
                        for c in r["parameters"]["required_status_checks"]}


def test_status_required_contexts_is_the_same_set(tmp_path):
    spec = importlib.util.spec_from_file_location("status", TOOLS / "status.py")
    status = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(status)
    checks = write_checks(tmp_path, {"required": ["lint-docs"]})
    assert status.required_contexts(str(RULESET), checks) == ruleset.contexts(str(RULESET), checks)
    assert status.required_contexts(str(RULESET), checks) == TEMPLATE | {"lint-docs"}
    broken = write_checks(tmp_path, {"required": ["Lint"]})
    assert status.required_contexts(str(RULESET), broken) is None  # malformed: every check counts, as before


def test_checks_json_is_a_security_path_and_owner_guarded():
    diff = ("diff --git a/.agents/checks.json b/.agents/checks.json\n"
            "--- a/.agents/checks.json\n+++ b/.agents/checks.json\n@@ -1 +1 @@\n-x\n+y\n")
    assert risk.classify(diff) == "security"
    codeowners = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    assert risk.owned_by(".agents/checks.json", codeowners, "Bankaifan")
