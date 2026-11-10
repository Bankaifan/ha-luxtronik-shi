"""Registry migration of renamed keys and the raw values added after 0.8.2."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik_shi.const import CONF_SLAVE, DOMAIN
from custom_components.luxtronik_shi.registers import (
    ALL_REGISTERS,
    BY_KEY,
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
    # the reference installation's entity ID of the raw value 10113 (0.9 ... 0.17.x)
    "raw_10113": "sensor.warmepumpe_diagnose_rohwert_10113",
    # the demand borders of the reference installation (keys renamed in 0.18.0)
    "heating_limit": "sensor.warmepumpe_heizung_anforderungsgrenze",
    "dhw_limit": "sensor.warmepumpe_warmwasser_anforderungsgrenze",
    # the availability flags of discrete 10000/10001 (keys renamed in 0.18.0)
    "cap_heating": "binary_sensor.warmepumpe_ausstattung_heizen",
    "cap_hot_water": "binary_sensor.warmepumpe_ausstattung_warmwasser",
}
# generated entity IDs follow the new name (test language: English); all others keep their ID
NEW_ENTITY_IDS = {
    **OLD_ENTITY_IDS,
    "cap_heating": "binary_sensor.warmepumpe_heating_available_equipped_mode_not_off",
    "cap_hot_water": "binary_sensor.warmepumpe_hot_water_available_equipped_mode_not_off",
}


def _domain(old_key: str) -> str:
    return BY_KEY[RENAMED_KEYS[old_key]].platform


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
    domain = _domain(key)
    return er.async_get(hass).async_get_or_create(
        domain,
        DOMAIN,
        f"{entry.entry_id}_{key}",
        config_entry=entry,
        suggested_object_id=entity_id.removeprefix(f"{domain}."),
        disabled_by=disabled_by,
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_renamed_entities_keep_their_registry_entry(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = _entry(hass, shi)
    old = {key: _create_old(hass, entry, key) for key in RENAMED_KEYS}
    assert {key: reg.entity_id for key, reg in old.items()} == OLD_ENTITY_IDS

    await _setup(hass, entry)

    registry = er.async_get(hass)
    for old_key, new_key in RENAMED_KEYS.items():
        # same registry entry (same internal id), same entity ID, new unique ID
        domain = _domain(old_key)
        assert registry.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{new_key}") == NEW_ENTITY_IDS[old_key]
        assert registry.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{old_key}") is None
        migrated = registry.async_get(NEW_ENTITY_IDS[old_key])
        assert migrated.id == old[old_key].id
        assert migrated.unique_id == f"{entry.entry_id}_{new_key}"
        assert migrated.disabled_by is None
        if domain == "sensor":
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
        assert registry.async_get_entity_id(_domain(old_key), DOMAIN, f"{entry.entry_id}_{old_key}") is None
        assert registry.async_get_entity_id(_domain(old_key), DOMAIN, f"{entry.entry_id}_{new_key}")
    assert hass.states.get(registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_heat_source_input"))
    # max_flow_temp is a diagnostic value that stays disabled by default, as raw_10112 was
    flow_max = registry.async_get(registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_max_flow_temp"))
    assert flow_max.disabled_by is er.RegistryEntryDisabler.INTEGRATION


def test_added_raw_registers_come_from_python_luxtronik() -> None:
    """Addresses of the ``unknown_input_*`` definitions that still have no proper entity (10060 became
    cfg_room_setpoint; 10410/10411, 10416/10417 and 10500-10502 became hours_cooling, hours_solar and the
    extra_dhw_* sensors, their raw twins are gone; 10352/10353 are only the binary sensors output_fp2/output_fp3
    since 0.18.0)."""
    assert RAW_INPUT_ADDRESSES_ADDED == (10412, 10413)
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
    assert "raw_10412" not in entry.runtime_data.data  # disabled by default: not polled
    for address in (10412, 10413):
        registry.async_update_entity(
            registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_raw_{address}"), disabled_by=None
        )
    await hass.async_block_till_done()
    data = entry.runtime_data.data
    assert data["raw_10412"] == 12
    assert data["raw_10413"] == 13
    for address in (10412, 10413):
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


def _entity_ids(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> tuple[er.EntityRegistry, str]:
    registry = er.async_get(hass)
    new = BY_KEY[key]
    entity_id = registry.async_get_entity_id(new.platform, DOMAIN, f"{entry.entry_id}_{key}")
    return registry, entity_id


async def test_generated_entity_id_of_renamed_key_is_renamed(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = _entry(hass, shi)
    old = er.async_get(hass).async_get_or_create(
        "binary_sensor", DOMAIN, f"{entry.entry_id}_cap_heating", config_entry=entry,
        suggested_object_id="warmepumpe_ausstattung_heizen",
    )
    await _setup(hass, entry)
    registry, entity_id = _entity_ids(hass, entry, "heating_available")
    assert registry.async_get(entity_id).id == old.id
    assert entity_id == "binary_sensor.warmepumpe_heating_available_equipped_mode_not_off"
    assert registry.async_get("binary_sensor.warmepumpe_ausstattung_heizen") is None
    # second run is a no-op
    from custom_components.luxtronik_shi import async_migrate_renamed_entity_ids

    async_migrate_renamed_entity_ids(hass, entry)
    assert _entity_ids(hass, entry, "heating_available")[1] == entity_id


async def test_user_chosen_entity_id_is_untouched(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = _entry(hass, shi)
    er.async_get(hass).async_get_or_create(
        "binary_sensor", DOMAIN, f"{entry.entry_id}_cap_hot_water", config_entry=entry,
        suggested_object_id="my_hot_water_flag",
    )
    await _setup(hass, entry)
    assert _entity_ids(hass, entry, "hot_water_available")[1] == "binary_sensor.my_hot_water_flag"


async def test_entity_id_rename_skipped_on_conflict(hass: HomeAssistant, shi: FakeSHI, caplog) -> None:
    entry = _entry(hass, shi)
    registry = er.async_get(hass)
    target = "binary_sensor.warmepumpe_heating_available_equipped_mode_not_off"
    registry.async_get_or_create(
        "binary_sensor", "other", "x", suggested_object_id=target.removeprefix("binary_sensor.")
    )
    registry.async_get_or_create(
        "binary_sensor", DOMAIN, f"{entry.entry_id}_cap_heating", config_entry=entry,
        suggested_object_id="warmepumpe_ausstattung_heizen",
    )
    await _setup(hass, entry)
    assert _entity_ids(hass, entry, "heating_available")[1] == "binary_sensor.warmepumpe_ausstattung_heizen"
    assert "already taken" in caplog.text
