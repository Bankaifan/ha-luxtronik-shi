"""The generated dashboards: up to date, valid, and their predicted entity IDs match Home Assistant's."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest
import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify as ha_slugify
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik_shi.const import DOMAIN

from .fake_shi import FakeSHI

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("gen_dashboard", ROOT / "tools" / "gen_dashboard.py")
gen = importlib.util.module_from_spec(_spec)
sys.modules["gen_dashboard"] = gen  # dataclasses look the module up
_spec.loader.exec_module(gen)


def test_committed_dashboards_are_up_to_date():
    for path, text in gen.committed().items():
        assert path.exists(), f"{path.name} missing: run python tools/gen_dashboard.py"
        assert path.read_text(encoding="utf-8") == text, f"{path.name} is out of date: run python tools/gen_dashboard.py"


def test_no_stray_files_in_dashboards_folder():
    assert {p.name for p in (ROOT / "dashboards").iterdir()} == {p.name for p in gen.committed()}


@pytest.mark.parametrize("text", ["Wärmepumpe Heating Temperature: flow", "Straße: ÄÖÜ (x) / y", "a  b", "Mixing circuit 1: flow"])
def test_slugify_matches_home_assistant(text):
    assert gen.slugify(text) == ha_slugify(text)


def _all_entities(node):
    if isinstance(node, dict):
        if "entity" in node and isinstance(node["entity"], str):
            yield node["entity"]
        for value in node.values():
            yield from _all_entities(value)
    elif isinstance(node, list):
        for item in node:
            yield from _all_entities(item)


@pytest.mark.parametrize("path", sorted((ROOT / "dashboards").glob("*.yaml")), ids=lambda p: p.name)
def test_dashboard_structure(path):
    dashboard = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert dashboard["title"] and dashboard["views"]
    paths = [view["path"] for view in dashboard["views"]]
    assert len(paths) == len(set(paths))
    for view in dashboard["views"]:
        assert view["type"] == "sections" and view["sections"], view["path"]
        for section in view["sections"]:
            assert len(section["cards"]) >= 2  # the heading and at least one card
    for entity in _all_entities(dashboard):
        assert "." in entity and entity == entity.lower(), entity
        assert "None" not in entity


def test_only_the_hacs_view_uses_custom_cards():
    for path in (ROOT / "dashboards").glob("*.yaml"):
        has_custom = "custom:" in path.read_text(encoding="utf-8")
        assert has_custom == (".hacs." in path.name), path.name


def test_profiles_differ_by_optional_parts():
    basic = (ROOT / "dashboards" / "luxtronik_shi.basic.en.yaml").read_text(encoding="utf-8")
    full = (ROOT / "dashboards" / "luxtronik_shi.full.en.yaml").read_text(encoding="utf-8")
    assert "mixing_circuit_2_mode" not in basic and "pool_block" not in basic
    assert "mixing_circuit_2_mode" in full and "pool_block" in full


@pytest.mark.parametrize("lang", ["en", "de"])
async def test_predicted_entity_ids_match_the_registry(hass: HomeAssistant, shi: FakeSHI, lang: str, tmp_path):
    """Set the integration up in both languages and compare every predicted ID with the real one."""
    hass.config.language = lang
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Wärmepumpe",
        unique_id=f"127.0.0.1:{shi.port}:1",
        data={"host": "127.0.0.1", "port": shi.port, "slave": 1},
        options={"scan_interval": 30, "features": list(gen.registers.FEATURES)},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    real = {
        e.unique_id.removeprefix(f"{entry.entry_id}_"): e.entity_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    resolver = gen.Resolver(lang, "Wärmepumpe", gen.registers.FEATURES)
    checked = 0
    for key in resolver.info:
        predicted = resolver.eid(key)
        if predicted is None:
            continue
        assert key in real, f"{key} predicted but not created"
        assert real[key] == predicted, key
        checked += 1
    assert checked > 80

    # The exact lookup in a registry file finds the same IDs and leaves out disabled entities.
    file = tmp_path / "core.entity_registry"
    file.write_text(json.dumps({"data": {"entities": [
        {"platform": e.platform, "unique_id": e.unique_id, "entity_id": e.entity_id, "disabled_by": e.disabled_by}
        for e in registry.entities.values()
    ]}}))
    mapping = gen.read_registry(file, None)
    assert mapping["flow"] == real["flow"]
    assert gen.detect_features(mapping) == gen.registers.FEATURES
    assert "raw_10113" not in mapping  # disabled by default
    text = gen.build(lang, "Wärmepumpe", "full", mapping)
    assert real["flow"] in text


def test_dashboard_links_every_blueprint():
    listed = sorted(f"{name}.yaml" for name in gen.layout.BLUEPRINTS)
    assert listed == sorted(p.name for p in (ROOT / "blueprints" / "automation" / "luxtronik_shi").glob("*.yaml"))
