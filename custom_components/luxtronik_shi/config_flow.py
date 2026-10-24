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
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback

from .const import (
    CONF_SCAN_INTERVAL,
    CONF_SLAVE,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .modbus_client import LuxtronikModbusClient, ModbusCommError, ModbusIllegalAddress

_LOGGER = logging.getLogger(__name__)

# Return temperature - exists on every SHI and is cheap to read.
_PROBE_ADDRESS = 10100

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

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """First step: connection data."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(f"{host}:{user_input[CONF_PORT]}:{user_input[CONF_SLAVE]}")
            self._abort_if_unique_id_configured()
            error = await _async_probe(host, user_input[CONF_PORT], user_input[CONF_SLAVE])
            if error is None:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_HOST: host,
                        CONF_PORT: user_input[CONF_PORT],
                        CONF_SLAVE: user_input[CONF_SLAVE],
                    },
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input or {}),
            errors=errors,
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
    """Options: polling interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Required(CONF_SCAN_INTERVAL, default=current): _SCAN_INTERVAL}),
        )
