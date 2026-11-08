"""Add new entity keys to tests/fixtures/entity_contract.json (run from repo root).

The script only ever ADDS keys. Removing a key from the contract is a deliberate, manual
breaking change (edit the fixture, list the key in ``registers.REMOVED_KEYS``) and must be documented in the
CHANGELOG.
"""

import ast
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "custom_components" / "luxtronik_shi"))
import registers  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "entity_contract.json"

tree = ast.parse((ROOT / "custom_components" / "luxtronik_shi" / "binary_sensor.py").read_text(encoding="utf-8"))
bits = next(
    ast.literal_eval(node.value)
    for node in tree.body
    if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "STATUS_BITS"
)

contract: dict[str, list[str]] = json.loads(FIXTURE.read_text(encoding="utf-8"))
current: dict[str, set[str]] = {}
for reg in registers.ALL_REGISTERS:
    if reg.platform == "internal":
        continue  # read only, no entity
    current.setdefault(reg.platform, set()).add(reg.key)
current["climate"] = set(registers.CLIMATE_KEYS)
current["water_heater"] = set(registers.WATER_HEATER_KEYS)
current["select"] |= set(registers.BLOCK_SELECT_KEYS)
current["switch"] |= set(registers.BLOCK_SWITCH_KEYS)
current["sensor"] |= set(registers.DERIVED_SENSOR_KEYS) | {registers.FIRMWARE_SENSOR_KEY}
current.setdefault("binary_sensor", set()).update([bit[0] for bit in bits] + ["online"])

added = []
for platform, keys in current.items():
    known = set(contract.get(platform, []))
    for key in sorted(keys - known):
        added.append(f"{platform}.{key}")
    contract[platform] = sorted(known | keys)

FIXTURE.write_text(json.dumps(dict(sorted(contract.items())), indent=2) + "\n", encoding="utf-8")
print("added:", ", ".join(added) if added else "nothing")
