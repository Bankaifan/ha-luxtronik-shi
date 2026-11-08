"""Diagnostics download: expected content, no host/IP/MAC/unique ID in the output."""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.components.diagnostics import REDACTED
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_PORT
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik_shi.const import CONF_SLAVE, DOMAIN
from custom_components.luxtronik_shi.diagnostics import async_get_config_entry_diagnostics

from .fake_shi import FakeSHI


async def test_diagnostics(hass: HomeAssistant, shi: FakeSHI) -> None:
    mac = "aa:bb:cc:dd:ee:ff"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="WP 127.0.0.1",
        unique_id=f"127.0.0.1:{shi.port}:1",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: shi.port, CONF_SLAVE: 1, CONF_MAC: mac},
        options={"scan_interval": 30, "features": ["mk1"]},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    requests_before = len(shi.requests)

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert len(shi.requests) == requests_before  # no new Modbus reads
    for key in ("integration_version", "home_assistant_version", "config_entry", "features", "firmware", "blocks"):
        assert key in diag
    manifest = json.loads((Path(__file__).parent.parent / "custom_components/luxtronik_shi/manifest.json").read_text())
    assert diag["integration_version"] == manifest["version"]
    assert diag["features"]["selected"] == ["mk1"]
    assert set(diag["features"]["capability_flags"]) == {
        "mk1", "mk2", "mk3", "cooling", "pool", "room_unit", "solar"
    }
    assert set(diag["firmware"]) == {"fw_version_major", "fw_version_minor", "fw_version_patch", "version"}
    assert diag["firmware"]["version"] == "3.92.3"
    assert diag["config_entry"]["data"][CONF_HOST] == REDACTED
    assert diag["config_entry"]["data"][CONF_MAC] == REDACTED

    regs = {k: v for block in diag["blocks"].values() for k, v in block["registers"].items()}
    assert {"flow", "return", "outside"} <= set(regs)
    assert all({"address", "raw", "value"} == set(v) for v in regs.values())
    assert regs["flow"]["value"] is not None
    assert regs["flow"]["raw"] is not None

    dump = json.dumps(diag)
    assert "127.0.0.1" not in dump
    assert mac not in dump
    assert entry.unique_id not in dump


async def test_diagnostics_polling_section(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Poll duration, failure counters and the last success come from memory (no Modbus access)."""
    from .test_integration import _setup
    from .test_repairs import Outage

    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    diag = await async_get_config_entry_diagnostics(hass, entry)
    polling = diag["polling"]
    assert polling["polls"] == 1 and polling["failed_polls"] == 0
    assert polling["last_poll_seconds"] is not None and polling["last_poll_seconds"] >= 0
    assert polling["last_success"] is not None and polling["last_failure"] is None
    assert "max_flow_temp" in polling["registers_not_polled"]  # disabled by default
    assert polling["registers_polled"] == len(coordinator.polled_registers)

    outage = Outage(coordinator)
    outage.down()
    await coordinator.async_refresh()
    requests_before = len(shi.requests)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert len(shi.requests) == requests_before
    polling = diag["polling"]
    assert polling["failed_polls"] == 1 and polling["failed_in_a_row"] == 1
    assert polling["last_failure"] is not None and polling["last_error"]
    assert "127.0.0.1" not in json.dumps(diag)
