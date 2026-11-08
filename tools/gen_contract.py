"""Add new entity keys to tests/fixtures/entity_contract.json (run from repo root).

The fixture lists every entity of the integration as ``platform -> keys``; ``tests/test_contract.py`` compares it
with the code in both directions, so every change of the entity set is visible in the diff of the fixture.

The script only ever ADDS keys. Removing a key, renaming it or moving it to another platform is a deliberate
breaking change: edit the fixture by hand, list the key in ``registers.REMOVED_KEYS`` (no entity left),
``registers.REMOVED_ENTITIES`` (moved to another platform) or ``registers.RENAMED_KEYS`` (registry migration), and
document it under *Action required* in the CHANGELOG. Keys that are in the fixture but no longer in the code are
printed as *stale* so that they are not forgotten.
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from contract import current_entities  # noqa: E402  (shared with tests/test_contract.py)

FIXTURE = ROOT / "tests" / "fixtures" / "entity_contract.json"

contract: dict[str, list[str]] = json.loads(FIXTURE.read_text(encoding="utf-8"))
current = current_entities()

added = []
stale = []
for platform, keys in current.items():
    known = set(contract.get(platform, []))
    for key in sorted(keys - known):
        added.append(f"{platform}.{key}")
    contract[platform] = sorted(known | keys)
for platform, keys in contract.items():
    for key in keys:
        if key not in current.get(platform, set()):
            stale.append(f"{platform}.{key}")

FIXTURE.write_text(json.dumps(dict(sorted(contract.items())), indent=2) + "\n", encoding="utf-8")
print("added:", ", ".join(added) if added else "nothing")
if stale:
    print("stale (in the fixture, not in the code; remove by hand if intended):", ", ".join(stale))
