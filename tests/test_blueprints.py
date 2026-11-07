"""The blueprints load, validate, and (the two that act) do what they say against the simulated heat pump."""

from __future__ import annotations

import pathlib
import shutil

import pytest
from homeassistant.components.blueprint import models
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.components.input_boolean import DOMAIN as INPUT_BOOLEAN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.luxtronik_shi.const import DOMAIN

from .fake_shi import FakeSHI
from .test_integration import _setup

ROOT = pathlib.Path(__file__).resolve().parent.parent
BLUEPRINTS = sorted((ROOT / "blueprints" / "automation" / "luxtronik_shi").glob("*.yaml"))


@pytest.mark.parametrize("path", BLUEPRINTS, ids=lambda p: p.name)
def test_blueprint_is_valid(path: pathlib.Path):
    blueprint = models.Blueprint(load_yaml(str(path)), expected_domain="automation", schema=BLUEPRINT_SCHEMA)
    meta = blueprint.metadata
    assert meta["source_url"].endswith(f"/blueprints/automation/luxtronik_shi/{path.name}")
    assert "DE:" in meta["description"] and "EN:" in meta["description"]
    for name, spec in meta["input"].items():
        assert spec["name"] and "/" in spec["name"], f"{name}: name needs English and German"


async def _automation(hass: HomeAssistant, name: str, inputs: dict) -> None:
    target = pathlib.Path(hass.config.path("blueprints", "automation", "luxtronik_shi"))
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "blueprints" / "automation" / "luxtronik_shi" / f"{name}.yaml", target)
    assert await async_setup_component(
        hass,
        "automation",
        {"automation": {"alias": name, "use_blueprint": {"path": f"luxtronik_shi/{name}.yaml", "input": inputs}}},
    )
    await hass.async_block_till_done()


def _switch(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id("switch", DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id
    return entity_id


async def test_block_while_signal_blocks_and_releases(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    block = _switch(hass, entry, "heating_block")
    assert await async_setup_component(hass, INPUT_BOOLEAN, {INPUT_BOOLEAN: {"price_high": None}})
    await _automation(
        hass, "block_while_signal",
        {"signal": "input_boolean.price_high", "blocks": [block], "release": True, "max_minutes": 0},
    )
    assert hass.states.get(block).state == "off"
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": "input_boolean.price_high"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(block).state == "on"
    assert shi.holding[10050] == 1  # written to the simulated heat pump and read back
    await hass.services.async_call("input_boolean", "turn_off", {"entity_id": "input_boolean.price_high"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(block).state == "off"
    assert shi.holding[10050] == 0


async def test_block_without_release_stays(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    block = _switch(hass, entry, "dhw_block")
    assert await async_setup_component(hass, INPUT_BOOLEAN, {INPUT_BOOLEAN: {"sig": None}})
    await _automation(
        hass, "block_while_signal",
        {"signal": "input_boolean.sig", "blocks": [block], "release": False, "max_minutes": 0},
    )
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": "input_boolean.sig"}, blocking=True)
    await hass.async_block_till_done()
    await hass.services.async_call("input_boolean", "turn_off", {"entity_id": "input_boolean.sig"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(block).state == "on"


async def test_surplus_trigger_runs_start_and_end_actions(hass: HomeAssistant, freezer) -> None:
    events = async_capture_events(hass, "luxtronik_test")
    hass.states.async_set("sensor.surplus", "0")
    await _automation(
        hass, "surplus_trigger",
        {
            "value": "sensor.surplus", "upper": 1500, "lower": 300, "minutes": 5,
            "start_actions": [{"event": "luxtronik_test", "event_data": {"what": "start"}}],
            "end_actions": [{"event": "luxtronik_test", "event_data": {"what": "end"}}],
        },
    )
    from datetime import timedelta  # noqa: PLC0415

    from homeassistant.util import dt as dt_util  # noqa: PLC0415
    from pytest_homeassistant_custom_component.common import async_fire_time_changed  # noqa: PLC0415

    hass.states.async_set("sensor.surplus", "2000")
    await hass.async_block_till_done()
    assert not events  # not yet: the value has to hold for 5 minutes
    freezer.tick(timedelta(minutes=5, seconds=1))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert [e.data["what"] for e in events] == ["start"]
    hass.states.async_set("sensor.surplus", "100")
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=5, seconds=1))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert [e.data["what"] for e in events] == ["start", "end"]


async def test_notify_problems_reports_an_error_number_change(hass: HomeAssistant) -> None:
    events = async_capture_events(hass, "luxtronik_test")
    hass.states.async_set("binary_sensor.wp_online", "on")
    hass.states.async_set("sensor.wp_error", "0")
    hass.states.async_set("sensor.wp_mode", "heating")
    await _automation(
        hass, "notify_problems",
        {
            "online": "binary_sensor.wp_online", "error_number": "sensor.wp_error",
            "operating_mode": "sensor.wp_mode", "offline_minutes": 10, "lockout_minutes": 120,
            "notify": [{"event": "luxtronik_test", "event_data": {"message": "{{ message }}"}}],
        },
    )
    hass.states.async_set("sensor.wp_error", "unavailable")  # a lost connection is not an error number
    await hass.async_block_till_done()
    assert not events
    hass.states.async_set("sensor.wp_error", "7")
    await hass.async_block_till_done()
    hass.states.async_set("sensor.wp_error", "9")
    await hass.async_block_till_done()
    assert [e.data["message"].strip() for e in events] == ["Error number 7 -> 9 / Fehlernummer 7 -> 9"]
