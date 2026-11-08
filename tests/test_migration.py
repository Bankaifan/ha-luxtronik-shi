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
    # the reference installation's entity ID of the raw value 10113 (0.9 ... 0.16.x)
    "raw_10113": "sensor.warmepumpe_diagnose_rohwert_10113",
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
    assert hass.states.get(OLD_ENTITY_IDS["raw_10113"]).state == "0.8"  # raw 8 = 0.8 °C (flow_calc_max)
    # no second entity was created next to the migrated ones
    unique_ids = [e.unique_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)]
    assert len(unique_ids) == len(set(unique_ids))
    assert not [uid for uid in unique_ids if uid.endswith(tuple(f"_{key}" for key in RENAMED_KEYS))]


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
    """Addresses of the ``unknown_input_*`` definitions that still have no proper entity (10060 became
    cfg_room_setpoint; 10410/10411, 10416/10417 and 10500-10502 became hours_cooling, hours_solar and the
    extra_dhw_* sensors in 0.17.0, their raw twins are gone)."""
    assert RAW_INPUT_ADDRESSES_ADDED == (10352, 10353, 10412, 10413)
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

    registry = er.async_get(hass)
    assert "raw_10352" not in entry.runtime_data.data  # disabled by default: not polled
    for address in (10352, 10412):
        registry.async_update_entity(
            registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_raw_{address}"), disabled_by=None
        )
    await hass.async_block_till_done()
    data = entry.runtime_data.data
    assert data["raw_10352"] == 52
    assert data["raw_10412"] == 12
    for address in (10352, 10412):
        registry.async_update_entity(
            registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_raw_{address}"),
            disabled_by=er.RegistryEntryDisabler.INTEGRATION,
        )
    for address in (*RAW_INPUT_ADDRESSES_ADDED, *RAW_HOLDING_ADDRESSES_ADDED):
        entity = registry.async_get(registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_raw_{address}"))
        assert entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_unused_sub_devices_can_be_removed(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Cooling and pool switched off: their devices may be deleted; the main device and used ones may not."""
    from homeassistant.helpers import device_registry as dr

    from custom_components.luxtronik_shi import async_remove_config_entry_device

    entry = _entry(hass, shi, {"scan_interval": 30, "features": ["mk1", "cooling", "pool"]})
    await _setup(hass, entry)
    devices = dr.async_get(hass)

    def device(area: str | None):
        suffix = f"_{area}" if area else ""
        wanted = (DOMAIN, f"{entry.entry_id}{suffix}")
        found = [d for d in dr.async_entries_for_config_entry(devices, entry.entry_id) if wanted in d.identifiers]
        return found[0] if found else None

    assert device("pool") and device("cooling")
    hass.config_entries.async_update_entry(entry, options={"scan_interval": 30, "features": ["mk1"]})
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.active_areas() == {None, "heating", "hot_water"}
    assert await async_remove_config_entry_device(hass, entry, device("pool")) is True
    assert await async_remove_config_entry_device(hass, entry, device("cooling")) is True
    assert await async_remove_config_entry_device(hass, entry, device("heating")) is False
    assert await async_remove_config_entry_device(hass, entry, device(None)) is False
