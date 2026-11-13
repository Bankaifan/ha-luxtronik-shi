"""CLAUDE.md imports AGENTS.md and the optional AGENTS.project.md (design 0016 section 4.2)."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def imports(path):
    return [line.strip() for line in (ROOT / path).read_text(encoding="utf-8").splitlines() if line.strip().startswith("@")]


def test_claude_md_imports_agents_then_project_file():
    assert imports("CLAUDE.md") == ["@AGENTS.md", "@AGENTS.project.md"]


def test_project_file_exists_so_the_import_resolves():
    assert (ROOT / "AGENTS.project.md").is_file()


def test_agents_md_names_the_project_file():
    assert "AGENTS.project.md" in (ROOT / "AGENTS.md").read_text(encoding="utf-8")


def test_agents_md_is_within_its_size_cap():
    budgets = json.loads((ROOT / "docs" / "budgets.json").read_text(encoding="utf-8"))
    assert (ROOT / "AGENTS.md").stat().st_size <= budgets["files"]["AGENTS.md"]
