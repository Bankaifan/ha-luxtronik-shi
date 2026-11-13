import importlib.util
import pathlib

_path = pathlib.Path(__file__).parent.parent.parent / "tools" / "check" / "check_var_defaults.py"
_spec = importlib.util.spec_from_file_location("check_var_defaults", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

REPO_WORKFLOWS = pathlib.Path(__file__).parent.parent.parent / ".github" / "workflows"


def test_unset_variable_compared_with_not_equal_is_flagged():
    # The scout bug: an unset variable reads as 0, so this is false and the job is skipped.
    text = "    if: vars.IDEAS_PER_WEEK != '0'\n"
    assert [(n, name) for n, name, _ in mod.findings(text)] == [(1, "IDEAS_PER_WEEK")]


def test_reversed_operands_are_flagged():
    assert [name for _, name, _ in mod.findings("if: '0' != vars.IDEAS_PER_WEEK\n")] == ["IDEAS_PER_WEEK"]


def test_explicit_empty_string_case_passes():
    text = "    if: vars.IDEAS_PER_WEEK == '' || vars.IDEAS_PER_WEEK != '0'\n"
    assert mod.findings(text) == []


def test_effective_value_form_passes():
    # The form used in scout.yml: the default is applied before the comparison, so no bare `vars.X != '...'`.
    assert mod.findings("    if: (vars.IDEAS_PER_WEEK || '3') != '0'\n") == []


def test_equality_is_not_flagged():
    # Opt-in switches: unset means off, which is the documented default.
    assert mod.findings("    if: vars.ORCHESTRATOR_ENABLED == 'true' && x\n") == []


def test_only_the_offending_line_is_reported():
    text = "a: 1\n    if: vars.STATUS_INTERVAL != '5'\nb: 2\n"
    assert [no for no, _, _ in mod.findings(text)] == [2]


def test_main_fails_on_bad_workflow(tmp_path, capsys):
    (tmp_path / "bad.yml").write_text("    if: vars.IDEAS_PER_WEEK != '0'\n", encoding="utf-8")
    assert mod.main(["check", str(tmp_path)]) == 1
    assert "IDEAS_PER_WEEK" in capsys.readouterr().out


def test_main_passes_on_clean_workflow(tmp_path, capsys):
    (tmp_path / "ok.yml").write_text("    if: (vars.IDEAS_PER_WEEK || '3') != '0'\n", encoding="utf-8")
    assert mod.main(["check", str(tmp_path)]) == 0
    assert "ok" in capsys.readouterr().out


def test_repository_workflows_are_clean():
    # Guards the real workflows: a new bare `vars.X != '...'` condition fails make check.
    assert mod.main(["check", str(REPO_WORKFLOWS)]) == 0
