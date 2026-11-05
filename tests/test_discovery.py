"""DHCP discovery: offer only real SHI devices, follow IP changes of known heat pumps."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import SOURCE_DHCP
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik_shi import config_flow
from custom_components.luxtronik_shi.const import CONF_SLAVE, DOMAIN

from .fake_shi import FakeSHI, free_port

MAC = "000e8c123456"
FORMATTED_MAC = "00:0e:8c:12:34:56"


def _dhcp(ip: str = "127.0.0.1") -> DhcpServiceInfo:
    return DhcpServiceInfo(ip=ip, hostname="wp-novelan", macaddress=MAC)


@pytest.fixture
def discovery_port(monkeypatch, shi: FakeSHI) -> int:
    monkeypatch.setattr(config_flow, "DISCOVERY_PORT", shi.port)
    return shi.port


async def test_discovered_heat_pump_is_offered(hass: HomeAssistant, discovery_port: int) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp())
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_NAME: "Wärmepumpe"})
    assert result["step_id"] == "equipment"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"mk1": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "127.0.0.1", CONF_PORT: discovery_port, CONF_SLAVE: 1, CONF_MAC: FORMATTED_MAC}
    await hass.async_block_till_done()


async def test_known_mac_with_new_ip_updates_entry(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="10.0.0.9:502:1",
        data={CONF_HOST: "10.0.0.9", CONF_PORT: shi.port, CONF_SLAVE: 1, CONF_MAC: FORMATTED_MAC},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp())
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "127.0.0.1"
    await hass.async_block_till_done()


async def test_known_ip_learns_mac(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Entries created by hand (like the reference installation) get the MAC on first discovery."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"127.0.0.1:{shi.port}:1",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: shi.port, CONF_SLAVE: 1},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp())
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_MAC] == FORMATTED_MAC
    assert entry.data[CONF_HOST] == "127.0.0.1"


async def test_device_without_shi_is_ignored(hass: HomeAssistant, monkeypatch, socket_enabled) -> None:
    monkeypatch.setattr(config_flow, "DISCOVERY_PORT", free_port())
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp())
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"
