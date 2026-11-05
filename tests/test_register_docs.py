"""docs/registers.md must match the register map (regenerate with tools/gen_register_docs.py)."""

from __future__ import annotations

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "registers.md"

_spec = importlib.util.spec_from_file_location("gen_register_docs", ROOT / "tools" / "gen_register_docs.py")
gen_register_docs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen_register_docs)


def test_registers_doc_is_up_to_date():
    assert DOC.read_text(encoding="utf-8") == gen_register_docs.render(), (
        "docs/registers.md is out of date: run python tools/gen_register_docs.py"
    )
