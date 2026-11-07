"""Config flow for the Luxtronik SHI (Modbus) integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .const import (
    CONF_FEATURES,
    CONF_RESTORE_AFTER_RESET,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE,
    DEFAULT_PORT,
    DEFAULT_RESTORE_AFTER_RESET,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .modbus_client import LuxtronikModbusClient, ModbusCommError, ModbusIllegalAddress
from .registers import BY_KEY, FEATURE_CAPABILITY, FEATURES

_LOGGER = logging.getLogger(__name__)

# Return temperature - exists on every SHI and is cheap to read.
_PROBE_ADDRESS = 10100

# Port and unit ID tried for a heat pump found via DHCP (module level so tests can point it at the simulator).
DISCOVERY_PORT = DEFAULT_PORT
DISCOVERY_SLAVE = DEFAULT_SLAVE

_SCAN_INTERVAL = vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL))


async def _async_probe(host: str, port: int, slave: int) -> str | None:
    """Try to read one register. Returns an error key or None on success."""
    client = LuxtronikModbusClient(host, port, slave, timeout=5.0)
    try:
        await client.read("input", _PROBE_ADDRESS, 1)
    except ModbusCommError as err:
        _LOGGER.debug("Verbindungstest zu %s:%s fehlgeschlagen: %s", host, port, err)
        return "cannot_connect"
    except ModbusIllegalAddress as err:
        _LOGGER.debug("Verbindungstest zu %s:%s: unerwartete Antwort: %s", host, port, err)
        return "not_supported"
    finally:
        await client.close()
    return None


async def _async_read_equipment(host: str, port: int, slave: int) -> list[str]:
    """Pre-select the optional parts the heat pump reports via its capability flags.

    A flag that cannot be read counts as present, so nothing is hidden by mistake.
    """
    client = LuxtronikModbusClient(host, port, slave, timeout=5.0)
    found: list[str] = []
    try:
        for feature in FEATURES:
            reg = BY_KEY[FEATURE_CAPABILITY[feature]]
            try:
                present = bool((await client.read(reg.kind, reg.address, 1))[0])
            except (ModbusCommError, ModbusIllegalAddress):
                present = True
            if present:
                found.append(feature)
    finally:
        await client.close()
    return found


def _equipment_schema(selected: list[str]) -> dict:
    return {vol.Required(feature, default=feature in selected): bool for feature in FEATURES}


def _selected(user_input: dict[str, Any]) -> list[str]:
    return [feature for feature in FEATURES if user_input.get(feature)]


def _user_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "Wärmepumpe")): str,
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, vol.UNDEFINED)): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=65535)
            ),
            vol.Required(CONF_SLAVE, default=defaults.get(CONF_SLAVE, DEFAULT_SLAVE)): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=247)
            ),
        }
    )


class LuxtronikConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the setup of a heat pump."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._title = ""
        self._detected: list[str] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """First step: connection data."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(f"{host}:{user_input[CONF_PORT]}:{user_input[CONF_SLAVE]}")
            self._abort_if_unique_id_configured()
            error = await _async_probe(host, user_input[CONF_PORT], user_input[CONF_SLAVE])
            if error is None:
                self._title = user_input[CONF_NAME]
                self._data = {
                    CONF_HOST: host,
                    CONF_PORT: user_input[CONF_PORT],
                    CONF_SLAVE: user_input[CONF_SLAVE],
                }
                self._detected = await _async_read_equipment(
                    host, user_input[CONF_PORT], user_input[CONF_SLAVE]
                )
                return await self.async_step_equipment()
            errors["base"] = error
        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        """A device with a Luxtronik MAC prefix or hostname appeared on the network.

        Only offered if its Smart Home Interface answers on Modbus/TCP. Known heat pumps are matched by MAC
        address (new IP addresses are taken over) or by IP address (the MAC is stored for next time).
        """
        host = discovery_info.ip
        mac = format_mac(discovery_info.macaddress)
        for entry in self._async_current_entries(include_ignore=False):
            if entry.data.get(CONF_MAC) == mac:
                if entry.data.get(CONF_HOST) != host:
                    _LOGGER.info("Wärmepumpe %s hat eine neue IP-Adresse: %s", mac, host)
                    self.hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_HOST: host})
                    self.hass.config_entries.async_schedule_reload(entry.entry_id)
                return self.async_abort(reason="already_configured")
            if entry.data.get(CONF_HOST) == host:
                if CONF_MAC not in entry.data:
                    self.hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_MAC: mac})
                return self.async_abort(reason="already_configured")

        await self.async_set_unique_id(f"{host}:{DISCOVERY_PORT}:{DISCOVERY_SLAVE}")
        self._abort_if_unique_id_configured()
        if await _async_probe(host, DISCOVERY_PORT, DISCOVERY_SLAVE) is not None:
            # Not a Luxtronik with Modbus/TCP enabled (or not reachable): stay silent.
            return self.async_abort(reason="not_supported")
        self._data = {CONF_HOST: host, CONF_PORT: DISCOVERY_PORT, CONF_SLAVE: DISCOVERY_SLAVE, CONF_MAC: mac}
        self.context["title_placeholders"] = {"host": host}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered heat pump and give it a name."""
        if user_input is not None:
            self._title = user_input[CONF_NAME]
            host, port, slave = (self._data[k] for k in (CONF_HOST, CONF_PORT, CONF_SLAVE))
            self._detected = await _async_read_equipment(host, port, slave)
            return await self.async_step_equipment()
        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=vol.Schema({vol.Required(CONF_NAME, default="Wärmepumpe"): str}),
            description_placeholders={"host": self._data[CONF_HOST]},
        )

    async def async_step_equipment(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Second step: which optional parts the installation has."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._title,
                data=self._data,
                options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL, CONF_FEATURES: _selected(user_input)},
            )
        return self.async_show_form(
            step_id="equipment", data_schema=vol.Schema(_equipment_schema(self._detected))
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change host, port or unit id of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            error = await _async_probe(host, user_input[CONF_PORT], user_input[CONF_SLAVE])
            if error is None:
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=f"{host}:{user_input[CONF_PORT]}:{user_input[CONF_SLAVE]}",
                    data_updates={
                        CONF_HOST: host,
                        CONF_PORT: user_input[CONF_PORT],
                        CONF_SLAVE: user_input[CONF_SLAVE],
                    },
                )
            errors["base"] = error
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str,
                vol.Required(CONF_PORT, default=entry.data[CONF_PORT]): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
                vol.Required(CONF_SLAVE, default=entry.data[CONF_SLAVE]): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=247)
                ),
            }
        )
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> LuxtronikOptionsFlow:
        """Return the options flow."""
        return LuxtronikOptionsFlow()


class LuxtronikOptionsFlow(OptionsFlowWithReload):
    """Options: polling interval, installation equipment and restore after a device reset."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    CONF_FEATURES: _selected(user_input),
                    CONF_RESTORE_AFTER_RESET: user_input[CONF_RESTORE_AFTER_RESET],
                }
            )
        options = self.config_entry.options
        restore = options.get(CONF_RESTORE_AFTER_RESET, DEFAULT_RESTORE_AFTER_RESET)
        current = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        # Entries created before 0.3.0 have no equipment option and still show everything.
        selected = options.get(CONF_FEATURES, list(FEATURES))
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): _SCAN_INTERVAL,
                    **_equipment_schema(selected),
                    vol.Required(CONF_RESTORE_AFTER_RESET, default=restore): bool,
                }
            ),
        )
