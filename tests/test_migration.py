"""Registry migration of renamed keys and the raw values added after 0.8.2."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik_shi.const import CONF_SLAVE, DOMAIN
from custom_components.luxtronik_shi.registers import (
    ALL_REGISTERS,
    RAW_HOLDING_ADDRESSES_ADDED,
    RAW_INPUT_ADDRESSES_ADDED,
    RENAMED_KEYS,
    active_registers,
)

from .fake_shi import FakeSHI

OLD_ENTITY_IDS = {
    "raw_10109": "sensor.waermepumpe_temperatur_aussen_mittelwert",
    "raw_10110": "sensor.waermepumpe_temperatur_waermequelle_eintritt",
    "raw_10112": "sensor.waermepumpe_rohwert_vorlauf_maximum_10112",
}


def _entry(hass: HomeAssistant, shi: FakeSHI, options: dict | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="WP",
        unique_id=f"127.0.0.1:{shi.port}:1",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: shi.port, CONF_SLAVE: 1},
        options={"scan_interval": 30, "features": ["mk1"]} if options is None else options,
    )
    entry.add_to_hass(hass)
    return entry


def _create_old(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    key: str,
    disabled_by: er.RegistryEntryDisabler | None = None,
) -> er.RegistryEntry:
    """Registry entry as an installation of 0.8.2 or older has it (old key, entity ID chosen long ago)."""
    entity_id = OLD_ENTITY_IDS[key]
    return er.async_get(hass).async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_{key}",
        config_entry=entry,
        suggested_object_id=entity_id.removeprefix("sensor."),
        disabled_by=disabled_by,
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_renamed_entities_keep_their_entity_id(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = _entry(hass, shi)
    old = {key: _create_old(hass, entry, key) for key in RENAMED_KEYS}
    assert {key: reg.entity_id for key, reg in old.items()} == OLD_ENTITY_IDS

    await _setup(hass, entry)

    registry = er.async_get(hass)
    for old_key, new_key in RENAMED_KEYS.items():
        # same registry entry (same internal id), same entity ID, new unique ID
        assert registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{new_key}") == OLD_ENTITY_IDS[old_key]
        assert registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{old_key}") is None
        migrated = registry.async_get(OLD_ENTITY_IDS[old_key])
        assert migrated.id == old[old_key].id
        assert migrated.unique_id == f"{entry.entry_id}_{new_key}"
        assert migrated.disabled_by is None
        assert migrated.unit_of_measurement == "°C"
    # the entities deliver values under the old entity IDs; 10112 used to be a raw 7, now 0.7 °C
    assert hass.states.get(OLD_ENTITY_IDS["raw_10109"]).state == "0.5"
    assert hass.states.get(OLD_ENTITY_IDS["raw_10110"]).state == "0.6"
    assert hass.states.get(OLD_ENTITY_IDS["raw_10112"]).state == "0.7"
    # no second entity was created next to the migrated ones
    unique_ids = [e.unique_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)]
    assert len(unique_ids) == len(set(unique_ids))
    assert not [uid for uid in unique_ids if uid.endswith(("_raw_10109", "_raw_10110", "_raw_10112"))]


async def test_migration_keeps_disabled_state(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = _entry(hass, shi)
    old = _create_old(hass, entry, "raw_10112", er.RegistryEntryDisabler.INTEGRATION)

    await _setup(hass, entry)

    migrated = er.async_get(hass).async_get(old.entity_id)
    assert migrated.unique_id == f"{entry.entry_id}_max_flow_temp"
    assert migrated.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(old.entity_id) is None


async def test_migration_without_equipment_option(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Entries created before 0.3.0 have no equipment option and must be migrated as well."""
    entry = _entry(hass, shi, options={})
    old = _create_old(hass, entry, "raw_10110")

    await _setup(hass, entry)

    assert er.async_get(hass).async_get(old.entity_id).unique_id == f"{entry.entry_id}_heat_source_input"
    assert hass.states.get(old.entity_id).state == "0.6"


async def test_migration_does_not_overwrite_existing_entity(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = _entry(hass, shi)
    registry = er.async_get(hass)
    old = _create_old(hass, entry, "raw_10110")
    new = registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_heat_source_input", config_entry=entry, suggested_object_id="other"
    )

    await _setup(hass, entry)

    assert registry.async_get(new.entity_id).unique_id == f"{entry.entry_id}_heat_source_input"
    assert registry.async_get(old.entity_id).unique_id == f"{entry.entry_id}_raw_10110"


async def test_new_installation_has_only_the_new_keys(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = _entry(hass, shi)
    await _setup(hass, entry)

    registry = er.async_get(hass)
    for old_key, new_key in RENAMED_KEYS.items():
        assert registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{old_key}") is None
        assert registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{new_key}")
    assert hass.states.get(registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_heat_source_input"))
    # max_flow_temp is a diagnostic value that stays disabled by default, as raw_10112 was
    flow_max = registry.async_get(registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_max_flow_temp"))
    assert flow_max.disabled_by is er.RegistryEntryDisabler.INTEGRATION


def test_added_raw_registers_come_from_python_luxtronik() -> None:
    """Addresses of the ``unknown_input_*`` definitions that had no key yet (10060 became cfg_room_setpoint)."""
    assert RAW_INPUT_ADDRESSES_ADDED == (10352, 10353, 10410, 10411, 10412, 10413, 10416, 10417, 10500, 10501, 10502)
    assert RAW_HOLDING_ADDRESSES_ADDED == ()
    by_key = {reg.key: reg for reg in ALL_REGISTERS}
    for address in RAW_INPUT_ADDRESSES_ADDED:
        reg = by_key[f"raw_{address}"]
        assert (reg.kind, reg.platform, reg.enabled_default, reg.diagnostic) == ("input", "sensor", False, True)
        assert reg.every >= 30


def test_added_raw_registers_not_polled_by_old_entries() -> None:
    """Entries without an equipment option keep their polling load."""
    legacy = {reg.key for reg in active_registers(None)}
    modern = {reg.key for reg in active_registers(["mk1"])}
    added = {f"raw_{a}" for a in (*RAW_INPUT_ADDRESSES_ADDED, *RAW_HOLDING_ADDRESSES_ADDED)}
    assert not legacy & added
    assert added <= modern


async def test_added_raw_registers_are_read_and_disabled(hass: HomeAssistant, shi: FakeSHI) -> None:
    for address in RAW_INPUT_ADDRESSES_ADDED:
        shi.input[address] = address % 100
    entry = _entry(hass, shi)
    await _setup(hass, entry)

    data = entry.runtime_data.data
    assert data["raw_10352"] == 52
    assert data["raw_10502"] == 2
    registry = er.async_get(hass)
    for address in (*RAW_INPUT_ADDRESSES_ADDED, *RAW_HOLDING_ADDRESSES_ADDED):
        entity = registry.async_get(registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_raw_{address}"))
        assert entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION
