import json
import pathlib

import design_origin
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DESIGN = "docs/design/0016-extension-points.md"


def _project(tmp_path, downstream):
    agents = tmp_path / ".agents"
    agents.mkdir(exist_ok=True)
    # a downstream managed.json without any template_designs key, as roblox_energy has it after sync (#674)
    (agents / "managed.json").write_text(json.dumps({"managed": []}), encoding="utf-8")
    if downstream:
        (agents / "template.json").write_text(json.dumps({"template": "Bankaifan/agent-template", "synced_sha": ""}),
                                              encoding="utf-8")
    return tmp_path


def test_the_template_repo_has_no_internal_designs(tmp_path):
    # no .agents/template.json: the template keeps splitting and parenting its own designs
    assert design_origin.template_internal(_project(tmp_path, downstream=False)) == set()


def test_a_downstream_project_gets_the_listed_designs_without_a_managed_key(tmp_path):
    assert design_origin.template_internal(_project(tmp_path, downstream=True)) == set(design_origin.TEMPLATE_DESIGNS)
    assert DESIGN in design_origin.template_internal(_project(tmp_path, downstream=True))


def test_a_project_without_managed_json_still_gets_the_list(tmp_path):
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents" / "template.json").write_text(json.dumps({"template": "Bankaifan/agent-template"}),
                                                        encoding="utf-8")
    assert DESIGN in design_origin.template_internal(tmp_path)


@pytest.mark.template_only  # docs/design/ studies are the template's; a project has other ones, or none
def test_every_design_of_the_template_is_listed():
    # a new design study of the template must be listed, or downstream projects split it (issue #674)
    shipped = {f"docs/design/{p.name}" for p in (ROOT / "docs" / "design").glob("[0-9][0-9][0-9][0-9]-*.md")}
    assert set(design_origin.TEMPLATE_DESIGNS) == shipped
