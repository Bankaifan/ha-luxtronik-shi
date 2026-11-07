"""Generate the ready-made Lovelace dashboards in ``dashboards/`` (run from the repo root).

Home Assistant builds an entity ID from the device name and the entity name in the language that was active when
the entity was created, so the IDs differ between installations. This script therefore does two things:

* **Predict** the entity IDs for a given device name and language the way Home Assistant builds them
  (``--name``, ``--lang``). This is how the committed example dashboards are made.
* **Look them up** exactly in your own entity registry (``--registry /config/.storage/core.entity_registry``).
  Entities that do not exist or are disabled are left out, optional parts (mixing circuits, cooling, pool, room
  unit) are detected from the entities that exist, and renamed entities are found by their unique ID.

Only the Python standard library and PyYAML are needed; Home Assistant is not imported.

    python tools/gen_dashboard.py                       # (re)generate the committed files in dashboards/
    python tools/gen_dashboard.py --registry /config/.storage/core.entity_registry --lang de > my.yaml
    python tools/gen_dashboard.py --name "Heat pump" --lang en --profile full --check

The dashboard layout itself is in ``tools/dashboard_layout.py``. Never edit the generated files by hand.
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import sys
import unicodedata
from dataclasses import dataclass

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
PKG = ROOT / "custom_components" / "luxtronik_shi"
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import dashboard_layout as layout  # noqa: E402
import registers  # noqa: E402  (plain import, no Home Assistant needed)

OUT = ROOT / "dashboards"
DEFAULT_NAME = "Wärmepumpe"  # the default title of a new config entry (config_flow.py)
PROFILES = {"basic": (), "full": registers.FEATURES}
LANGS = ("en", "de")
# Hand-written transliteration that python-slugify (text-unidecode) applies; the rest is NFKD without marks.
_TRANSLIT = {"ß": "ss", "ä": "a", "ö": "o", "ü": "u", "Ä": "A", "Ö": "O", "Ü": "U", "æ": "ae", "ø": "o"}


def slugify(text: str) -> str:
    """The object ID Home Assistant derives from a name (``homeassistant.util.slugify``, ASCII subset)."""
    text = "".join(_TRANSLIT.get(c, c) for c in text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    out: list[str] = []
    for char in text.lower():
        if char.isascii() and (char.isalnum()):
            out.append(char)
        elif out and out[-1] != "_":
            out.append("_")
    return "".join(out).strip("_")


@dataclass(frozen=True)
class Info:
    """What the generator knows about one entity key."""

    key: str
    platform: str
    area: str | None
    features: tuple[str, ...]
    enabled_default: bool
    writable: bool


def _status_bits() -> tuple[tuple, frozenset]:
    tree = ast.parse((PKG / "binary_sensor.py").read_text(encoding="utf-8"))
    bits: tuple = ()
    disabled: frozenset = frozenset()
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        if node.target.id == "STATUS_BITS":
            bits = ast.literal_eval(node.value)
        elif node.target.id == "_DISABLED_BY_DEFAULT":
            disabled = frozenset(ast.literal_eval(node.value.args[0]))
    return bits, disabled


def universe() -> dict[str, Info]:
    """Every entity key of this version of the integration (the same set as the entity contract)."""
    found: dict[str, Info] = {}
    for reg in registers.ALL_REGISTERS:
        if reg.platform == "internal":
            continue
        found[reg.key] = Info(
            reg.key, reg.platform, registers.area_of(reg.key), registers.features_of(reg),
            reg.enabled_default, reg.platform in ("switch", "number", "select"),
        )
    for sensor in registers.DERIVED_SENSORS:
        found[sensor.key] = Info(sensor.key, "sensor", registers.area_of(sensor.key), (), True, False)
    bits, disabled = _status_bits()
    for bit in bits:
        found[bit[0]] = Info(bit[0], "binary_sensor", None, (), bit[0] not in disabled, False)
    found["online"] = Info("online", "binary_sensor", None, (), True, False)
    for key in registers.CLIMATE_KEYS:
        found[key] = Info(key, "climate", "heating", (), True, True)
    for key in registers.WATER_HEATER_KEYS:
        found[key] = Info(key, "water_heater", "hot_water", (), True, True)
    return found


def _translations(lang: str) -> dict:
    return json.loads((PKG / "translations" / f"{lang}.json").read_text(encoding="utf-8"))


class Resolver:
    """Key -> entity ID, predicted or read from an entity registry."""

    def __init__(self, lang: str, name: str, features: tuple[str, ...], registry: dict[str, str] | None = None):
        self.lang = lang
        self.name = name
        self.info = universe()
        self.tr = _translations(lang)
        self.registry = registry
        self.features = features
        self._ids: dict[str, str] = {}
        for key, info in self.info.items():
            entity_id = self._lookup(info)
            if entity_id:
                self._ids[key] = entity_id

    # -- prediction -------------------------------------------------------------------------------------
    def _entity_name(self, info: Info) -> str | None:
        if info.platform in ("climate", "water_heater"):
            return None  # the entity carries the name of its device
        key = "raw" if info.key in registers.RAW_KEYS else info.key
        entry = self.tr["entity"].get(info.platform, {}).get(key)
        if entry is None:
            return None
        return entry["name"].replace("{address}", info.key.removeprefix("raw_"))

    def _predict(self, info: Info) -> str | None:
        if not info.enabled_default or not set(info.features) <= set(self.features):
            return None
        device = self.name
        if info.area:
            device = self.tr["device"][info.area]["name"].replace("{name}", self.name)
        entity = self._entity_name(info)
        if entity is None and info.platform not in ("climate", "water_heater"):
            return None
        label = device if entity is None else f"{device} {entity}"
        return f"{info.platform}.{slugify(label)}"

    def _lookup(self, info: Info) -> str | None:
        if self.registry is None:
            return self._predict(info)
        return self.registry.get(info.key)

    # -- queries ----------------------------------------------------------------------------------------
    def eid(self, key: str) -> str | None:
        return self._ids.get(key)

    def has(self, *keys: str) -> bool:
        return all(key in self._ids for key in keys)

    def label(self, key: str) -> str:
        """Friendly name Home Assistant shows for the key (device name plus entity name)."""
        info = self.info[key]
        device = self.name
        if info.area:
            device = self.tr["device"][info.area]["name"].replace("{name}", self.name)
        entity = self._entity_name(info)
        return device if entity is None else f"{device} {entity}"

    def all_known(self) -> dict[str, Info]:
        return self.info


def read_registry(path: pathlib.Path, entry_id: str | None) -> dict[str, str]:
    """Map entity key -> entity ID of one config entry from ``.storage/core.entity_registry``."""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = [e for e in data["data"]["entities"] if e.get("platform") == "luxtronik_shi"]
    if not rows:
        raise SystemExit("no luxtronik_shi entities found in the registry file")
    prefixes = {e["unique_id"].split("_", 1)[0] for e in rows}
    if entry_id is None:
        if len(prefixes) > 1:
            raise SystemExit(f"several heat pumps found, pick one with --entry-id: {sorted(prefixes)}")
        entry_id = next(iter(prefixes))
    mapping: dict[str, str] = {}
    for row in rows:
        prefix, _, key = row["unique_id"].partition("_")
        if prefix == entry_id and not row.get("disabled_by"):
            mapping[key] = row["entity_id"]
    return mapping


def detect_features(mapping: dict[str, str]) -> tuple[str, ...]:
    """Optional parts that have entities in the registry."""
    probe = {
        "mk1": "cfg_mk1_mode", "mk2": "cfg_mk2_mode", "mk3": "cfg_mk3_mode",
        "cooling": "cfg_mk1_cool_mode", "pool": "pool_block", "room_unit": "cfg_room_setpoint",
    }
    found = {f for f, key in probe.items() if key in mapping}
    if "cooling" not in found and "cooling_block" in mapping:
        found.add("cooling")
    return tuple(f for f in registers.FEATURES if f in found)


class _Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data):  # no &id001 anchors in a file people read
        return True


def _str(dumper: yaml.SafeDumper, value: str):
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _str)


def render(dashboard: dict, header: str) -> str:
    body = yaml.dump(dashboard, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=110, indent=2)
    return header + body


def build(lang: str, name: str, profile: str, registry: dict[str, str] | None = None, hacs: bool = False,
          features: tuple[str, ...] | None = None) -> str:
    if features is None:
        features = detect_features(registry) if registry is not None else PROFILES[profile]
    resolver = Resolver(lang, name, features, registry)
    dashboard = layout.build(resolver, lang, hacs=hacs)
    kind = layout.text(lang, "hacs_header" if hacs else "header")
    header = "".join(f"# {line}\n" for line in kind.format(name=name, profile=profile).splitlines()) + "\n"
    return render(dashboard, header)


def committed() -> dict[pathlib.Path, str]:
    """Every file under dashboards/ with its generated content."""
    files: dict[pathlib.Path, str] = {}
    for lang in LANGS:
        for profile in PROFILES:
            files[OUT / f"luxtronik_shi.{profile}.{lang}.yaml"] = build(lang, DEFAULT_NAME, profile)
        files[OUT / f"luxtronik_shi.hacs.{lang}.yaml"] = build(lang, DEFAULT_NAME, "full", hacs=True)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--lang", choices=LANGS, help="language of the texts and of predicted entity IDs")
    parser.add_argument("--name", default=DEFAULT_NAME, help="name of the heat pump device (config entry title)")
    parser.add_argument("--profile", choices=tuple(PROFILES), default="basic",
                        help="basic: no optional parts, full: all (ignored with --registry)")
    parser.add_argument("--registry", type=pathlib.Path, help="path to .storage/core.entity_registry")
    parser.add_argument("--entry-id", help="config entry ID when the registry has several heat pumps")
    parser.add_argument("--hacs", action="store_true", help="the optional view that needs HACS cards")
    parser.add_argument("--check", action="store_true", help="only compare the committed files, change nothing")
    args = parser.parse_args(argv)

    if args.lang is None and not args.registry:
        files = committed()
        if args.check:
            stale = [str(p.relative_to(ROOT)) for p, text in files.items()
                     if not p.exists() or p.read_text(encoding="utf-8") != text]
            if stale:
                print("out of date, run python tools/gen_dashboard.py:", *stale, sep="\n  ")
                return 1
            return 0
        OUT.mkdir(exist_ok=True)
        for path, text in files.items():
            path.write_text(text, encoding="utf-8")
            print("wrote", path.relative_to(ROOT))
        return 0

    lang = args.lang or "en"
    registry = read_registry(args.registry, args.entry_id) if args.registry else None
    sys.stdout.write(build(lang, args.name, args.profile, registry, hacs=args.hacs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
