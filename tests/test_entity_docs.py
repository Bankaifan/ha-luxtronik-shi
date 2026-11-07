"""docs/entities.md and docs/entities.de.md must match the code and document every entity.

Regenerate with ``python tools/gen_entity_docs.py``. A new entity key needs an explanation in
``tools/entity_docs_entries.py`` (the generator fails without one).
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTRACT = json.loads((ROOT / "tests" / "fixtures" / "entity_contract.json").read_text(encoding="utf-8"))

_spec = importlib.util.spec_from_file_location("gen_entity_docs", ROOT / "tools" / "gen_entity_docs.py")
gen = importlib.util.module_from_spec(_spec)
sys.modules["gen_entity_docs"] = gen  # dataclasses look the module up
_spec.loader.exec_module(gen)

LANGS = ("en", "de")


@pytest.mark.parametrize("lang", LANGS)
def test_entity_page_is_up_to_date(lang):
    assert gen.OUTPUTS[lang].read_text(encoding="utf-8") == gen.render(lang), (
        f"{gen.OUTPUTS[lang].relative_to(ROOT)} is out of date: run python tools/gen_entity_docs.py"
    )


@pytest.mark.parametrize("lang", LANGS)
def test_every_contract_key_is_documented(lang):
    page = gen.OUTPUTS[lang].read_text(encoding="utf-8")
    missing = [
        f"{platform}.{key}"
        for platform, keys in CONTRACT.items()
        for key in keys
        if f"`{key}`" not in page
    ]
    assert not missing, f"Contract keys missing from {gen.OUTPUTS[lang].name}: {missing}"


def test_every_current_entity_is_in_the_contract_and_described():
    """The generator raises for an entity without prose; every entity it lists is also in the contract."""
    for entity in gen.collect():
        gen._text(entity)  # raises MissingText
        assert entity.key in CONTRACT[entity.platform], f"{entity.platform}.{entity.key} not in the contract"


def test_no_explanation_for_an_unknown_key():
    known = {entity.key for entity in gen.collect()}
    stale = sorted(set(gen.entries.ENTRIES) - known)
    assert not stale, f"tools/entity_docs_entries.py describes keys that no entity has: {stale}"


def test_both_languages_have_the_same_rows():
    def rows(lang):
        return [line.split("|")[2].split("<br>")[0] for line in gen.render(lang).splitlines() if line.startswith("| ") and "<br>" in line]

    assert rows("en") == rows("de")
