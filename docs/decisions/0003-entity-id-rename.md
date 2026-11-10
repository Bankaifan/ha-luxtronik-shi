# 0003 Entity ID rename of renamed keys

Status: recorded from the #101 implementation (as it is in the code). Daniel's approval of this note: open. Not yet released.

## Decision
- When a key is renamed (0.18.0: `cap_heating` -> `heating_available`, `cap_hot_water` -> `hot_water_available`), the
  registry entry keeps its entity ID only if the ID is an auto-generated one. `async_migrate_renamed_entity_ids`
  renames it while the object ID still ends in the slug of the old display name (German or English, see
  `RENAMED_KEY_OLD_NAMES`).
- The new ID is slugified from the display name of the installation's language: `name_de` on a German-language Home
  Assistant (`heizen_verfugbar_ausgestattet_betriebsart_nicht_aus`), `name_en` otherwise
  (`heating_available_equipped_mode_not_off`). The same applies to `hot_water_available`.
- A user-chosen entity ID is never renamed. A target that is already taken is skipped and logged.
- Each rename and each skip is logged; a second run does nothing.
- Users whose automations or dashboards reference a renamed generated ID must update them (CHANGELOG *Action required*).

## Consequences
- The rename relies on the old display names being kept in `RENAMED_KEY_OLD_NAMES`; remove an entry only together
  with the migration that still needs it.
- A future renamed key whose display name changed needs its old names in `RENAMED_KEY_OLD_NAMES`, or its generated
  entity IDs are not migrated.
