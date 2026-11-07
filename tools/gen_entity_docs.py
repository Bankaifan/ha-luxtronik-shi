"""Generate docs/entities.md and docs/entities.de.md (run from repo root).

The entity list is derived from the code, not typed by hand: ``registers.py`` (all registers, derived sensors,
climate and water heater keys), ``binary_sensor.py`` (status bits, connection), ``const.py`` (restore and deferred
keys) and the generated translations (names and option texts). The prose lives in ``tools/entity_docs_texts.py``
and ``tools/entity_docs_entries.py``. A key without prose makes this script fail, so a new entity cannot be
forgotten. Never edit the generated pages by hand.
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parent.parent
PKG = ROOT / "custom_components" / "luxtronik_shi"
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import const  # noqa: E402
import entity_docs_entries as entries  # noqa: E402
import entity_docs_texts as texts  # noqa: E402
import registers  # noqa: E402

OUTPUTS = {"en": ROOT / "docs" / "entities.md", "de": ROOT / "docs" / "entities.de.md"}
PLATFORM_ORDER = ("sensor", "binary_sensor", "switch", "number", "select", "climate", "water_heater")
KIND_TABLE = {"input": "input", "holding": "holding", "discrete": "discrete input"}


class MissingText(Exception):
    """An entity has no explanation in tools/entity_docs_entries.py."""


@dataclass
class Entity:
    key: str
    platform: str
    order: int
    reg: registers.Register | None = None
    derived: registers.DerivedSensor | None = None
    bit: int | None = None
    enabled_default: bool = True
    diagnostic: bool = False
    config: bool = False
    area: str | None = None


def _binary_sensor_constants() -> tuple[tuple, frozenset]:
    """STATUS_BITS and _DISABLED_BY_DEFAULT of binary_sensor.py without importing Home Assistant."""
    tree = ast.parse((PKG / "binary_sensor.py").read_text(encoding="utf-8"))
    bits: tuple = ()
    disabled: frozenset = frozenset()
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        if node.target.id == "STATUS_BITS":
            bits = ast.literal_eval(node.value)
        elif node.target.id == "_DISABLED_BY_DEFAULT":
            call = node.value
            disabled = frozenset(ast.literal_eval(call.args[0])) if isinstance(call, ast.Call) else frozenset()
    return bits, disabled


def collect() -> list[Entity]:
    """Every entity of the integration, in display order."""
    bits, disabled = _binary_sensor_constants()
    found: list[Entity] = []
    for reg in registers.ALL_REGISTERS:
        found.append(
            Entity(
                reg.key, reg.platform, len(found), reg=reg, enabled_default=reg.enabled_default,
                diagnostic=reg.diagnostic, config=reg.config, area=registers.area_of(reg.key),
            )
        )
    for sensor in registers.DERIVED_SENSORS:
        found.append(Entity(sensor.key, "sensor", len(found), derived=sensor, area=registers.area_of(sensor.key)))
    for bit in bits:
        found.append(
            Entity(bit[0], "binary_sensor", len(found), bit=bit[1], enabled_default=bit[0] not in disabled)
        )
    found.append(Entity("online", "binary_sensor", len(found), diagnostic=True))
    for key, source in ((registers.CLIMATE_HEATING_KEY, "cfg_heating_setpoint"), (registers.WATER_HEATER_DHW_KEY, "cfg_dhw_setpoint")):
        platform = "climate" if key == registers.CLIMATE_HEATING_KEY else "water_heater"
        found.append(Entity(key, platform, len(found), area=registers.area_of(source)))
    return found


def _translations(lang: str) -> dict:
    path = PKG / "translations" / f"{lang}.json"
    return json.loads(path.read_text(encoding="utf-8"))["entity"]


def _text(entity: Entity) -> texts.Entry:
    entry = entries.ENTRIES.get(entity.key)
    if entry is None and entity.reg is not None and entity.key in registers.RAW_KEYS:
        en, de, src = entries.RAW_TEXT.get(entity.reg.address, entries.RAW_DEFAULT)
        entry = texts.Entry("raw", en, de, src)
    if entry is None:
        raise MissingText(
            f"No explanation for {entity.platform}.{entity.key}: add it to tools/entity_docs_entries.py"
        )
    return entry


def _name(entity: Entity, lang: str, trans: dict, page: dict) -> str:
    item = trans.get(entity.platform, {}).get(entity.key)
    if entity.key in registers.RAW_KEYS:
        item = trans.get("sensor", {}).get("raw")
        return item["name"].replace("{address}", str(entity.reg.address)) if item else entity.key
    if item and "name" in item:
        return item["name"]
    return page["no_name"]


def _states(entity: Entity, trans: dict) -> dict[str, str]:
    return trans.get(entity.platform, {}).get(entity.key, {}).get("state", {})


def _options(entity: Entity) -> tuple[str, ...] | None:
    if entity.reg is not None and entity.reg.options:
        return entity.reg.options
    return None


def _fmt(value: float, lang: str = "en") -> str:
    text = f"{value:g}"
    return text.replace(".", ",") if lang == "de" else text


def _unit(entity: Entity) -> str:
    if entity.reg is not None and entity.reg.unit:
        return entity.reg.unit
    if entity.derived is not None:
        return "-"
    return "-"


def _values(entity: Entity, entry: texts.Entry, lang: str, trans: dict, page: dict) -> str:
    reg = entity.reg
    states = _states(entity, trans)
    if entity.platform == "number" and reg is not None:
        parts = [f"{_fmt(reg.min_value, lang)} … {_fmt(reg.max_value, lang)} {reg.unit or ''}".strip()]
        if reg.step:
            parts.append(("step " if lang == "en" else "Schritt ") + _fmt(reg.step, lang))
        return "<br>".join(parts)
    if _options(entity) and reg is not None:
        return "<br>".join(f"{i} = `{opt}`: {states.get(opt, opt)}" for i, opt in enumerate(reg.options))
    if entity.platform == "switch":
        return page["switch_values"]
    if entity.platform == "binary_sensor":
        return page["on_off"]
    if entity.platform == "climate":
        return "<br>".join(f"`{k}`: {v}" for k, v in states.items())
    if entity.platform == "water_heater":
        return "<br>".join(f"`{k}`: {v}" for k, v in states.items())
    if entity.derived is not None:
        top = getattr(registers, "COP_MAX_PLAUSIBLE", None)
        return f"0 … {_fmt(top, lang)}" if top else page["none"]
    vals = entry.vals_en if lang == "en" else entry.vals_de
    return vals or page["none"]


def _where(entity: Entity, page: dict) -> str:
    if entity.reg is not None:
        where = f"{KIND_TABLE[entity.reg.kind]} {entity.reg.address}"
    elif entity.derived is not None:
        where = page["derived"]
    elif entity.bit is not None:
        where = f"heat_generator_state, bit {entity.bit}"
    elif entity.key == "online":
        where = "-"
    else:
        where = page["view"]
    device = page["devices"][entity.area]
    return f"{entity.platform} · {where} · {page['device_word']} {device}"


def _flags(entity: Entity, lang: str, page: dict) -> str:
    flags = page["flags"]
    out: list[str] = []
    if not entity.enabled_default:
        out.append(flags["disabled"])
    if entity.diagnostic:
        out.append(flags["diagnostic"])
    elif entity.config:
        out.append(flags["config"])
    if entity.reg is not None:
        needs = registers.features_of(entity.reg)
        if needs:
            out.append(flags["needs"].format(parts=" + ".join(page["features"][f] for f in needs)))
        if entity.reg.every > 1:
            out.append(flags["every"].format(n=entity.reg.every))
    if entity.key in const.RESTORE_KEYS:
        out.append(flags["restored"])
    if entity.key in const.DEFERRED_KEYS:
        out.append(flags["deferred"])
    return "; ".join(out)


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _slug(heading: str) -> str:
    """GitHub's anchor for a heading."""
    keep = [c for c in heading.lower() if c.isalnum() or c in " -_"]
    return "".join(keep).replace(" ", "-")


def _legend(lang: str) -> str:
    idx = 0 if lang == "en" else 1
    return "; ".join(f"**{code}** {text[idx]}" for code, text in texts.SOURCE_LEGEND.items())


def _section_title(index: int, section: texts.Section, lang: str) -> str:
    return f"{index}. {section.title_en if lang == 'en' else section.title_de}"


def render(lang: str) -> str:
    """Return the complete content of the page in ``lang`` (``en`` or ``de``)."""
    page = texts.PAGE[lang]
    trans = _translations(lang)
    ents = collect()
    sections = list(texts.SECTIONS)
    ids = {section.id for section in sections}
    by_section: dict[str, list[tuple[Entity, texts.Entry]]] = {section.id: [] for section in sections}
    for entity in ents:
        entry = _text(entity)
        if entry.section not in ids:
            raise MissingText(f"{entity.key}: unknown section {entry.section!r}")
        by_section[entry.section].append((entity, entry))

    out: list[str] = [f"# {page['title']}", "", page["lead"], "", f"> {page['generated']}", ""]
    out += [f"## {page['how_title']}", "", page["how"].format(legend=_legend(lang)), ""]

    counts = {p: sum(1 for e in ents if e.platform == p) for p in PLATFORM_ORDER}
    out += [f"## {page['overview_title']}", "", "| " + " | ".join(page["overview_cols"]) + " |", "|---|---|---|"]
    out += [f"| `{p}` | {counts[p]} | {page['platform_text'][p]} |" for p in PLATFORM_ORDER if counts[p]]
    out += ["", f"## {page['contents']}", ""]
    for i, section in enumerate(sections, 1):
        title = _section_title(i, section, lang)
        out.append(f"{i}. [{title.split('. ', 1)[1]}](#{_slug(title)})")
    extra = [page["pitfalls_title"], page["renamed_title"], page["index_title"], page["sources_title"]]
    out += [f"- [{t}](#{_slug(t)})" for t in extra]
    out.append("")

    cols = page["cols"]
    for i, section in enumerate(sections, 1):
        out += [f"## {_section_title(i, section, lang)}", "", section.intro_en if lang == "en" else section.intro_de, ""]
        rows = sorted(by_section[section.id], key=lambda pair: (pair[0].platform not in ("climate", "water_heater"), pair[0].order))
        if not rows:
            continue
        out += ["| " + " | ".join(cols) + " |", "|---|---|---|---|---|"]
        for entity, entry in rows:
            body = (entry.en if lang == "en" else entry.de).strip()
            if entry.src:
                body += f" *({entry.src})*"
            flags = _flags(entity, lang, page)
            if flags:
                body += f"<br>*{flags}*"
            name = _name(entity, lang, trans, page)
            key = f"`{entity.key}`<br>{_where(entity, page)}"
            out.append(
                "| " + " | ".join(
                    _cell(c) for c in (name, key, _unit(entity), _values(entity, entry, lang, trans, page), body)
                ) + " |"
            )
        out.append("")

    restored = ", ".join(f"`{k}`" for k in sorted(const.RESTORE_KEYS))
    out += [f"## {page['pitfalls_title']}", "", texts.PITFALLS[lang].format(restored=restored), ""]

    out += [f"## {page['renamed_title']}", "", page["renamed_text"], "", "| " + " | ".join(page["renamed_cols"]) + " |", "|---|---|"]
    out += [f"| `{old}` | `{new}` |" for old, new in sorted(registers.RENAMED_KEYS.items())]
    out.append("")

    titles = {s.id: _section_title(i, s, lang) for i, s in enumerate(sections, 1)}
    section_of = {e.key: _text(e).section for e in ents}
    out += [f"## {page['index_title']}", "", "| " + " | ".join(page["index_cols"]) + " |", "|---|---|---|"]
    for entity in sorted(ents, key=lambda e: e.key):
        title = titles[section_of[entity.key]]
        out.append(f"| `{entity.key}` | {entity.platform} | [{title}](#{_slug(title)}) |")
    out.append("")

    out += [f"## {page['sources_title']}", ""]
    out += [
        "* python-luxtronik: [Bouni/python-luxtronik](https://github.com/Bouni/python-luxtronik), "
        "`luxtronik/definitions/inputs.py`, `holdings.py`, `datatypes.py` (MIT).",
        "* [firmware-3.92.3-shi-analysis.md](firmware-3.92.3-shi-analysis.md), [registers.md](registers.md).",
    ]
    out += [f"* {name}: [{label}]({url})" for name, url, label in texts.WEB_SOURCES]
    out.append("")
    return "\n".join(out)


def main() -> None:
    for lang, path in OUTPUTS.items():
        path.write_text(render(lang), encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
