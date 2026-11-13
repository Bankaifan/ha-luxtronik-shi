import importlib.util
import json
import pathlib

import pytest

_path = pathlib.Path(__file__).parent.parent.parent / "tools" / "dependabot_update_type.py"
_spec = importlib.util.spec_from_file_location("dependabot_update_type", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Bump actions/checkout from 4.1.0 to 4.1.1", "patch"),
        ("Bump actions/checkout from 4.1.0 to 4.2.0", "minor"),
        ("Bump actions/checkout from 4 to 5", "major"),
        ("Bump actions/checkout from v4 to v5", "major"),
        ("Bump requests from 2.31.0 to 3.0.0", "major"),
        ("Bump foo from 0.3.1 to 0.4.0", "major"),
        ("Bump foo from 0.3.1 to 0.3.2", "patch"),
        ("Bump foo from 1.2.3 to 1.2.3", "major"),
        ("Bump foo from 1.3.0 to 1.2.0", "major"),
        ("Bump the actions group with 3 updates", "major"),
        ("Bump the pip group across 1 directory with 2 updates", "major"),
        ("Bump foo from abc to def", "major"),
        ("", "major"),
        # requirement ranges
        ("Update ruff requirement from >=0.5 to >=0.6", "major"),
        ("Update pytest requirement from >=8.0.0 to >=8.1.0", "minor"),
        ("Update pytest requirement from >=8.0.0 to >=8.0.2", "patch"),
        ("Update requests requirement from >=2.31,<3 to >=3.0,<4", "major"),
        ("Update requests requirement from >=2.31,<3 to >=2.32,<3", "minor"),
        ("Update requests requirement from >=2.31,<3 to >=2.31,<4", "major"),
        ("Update requests requirement from ~=2.31 to >=2.31,<3", "major"),
    ],
)
def test_classify_title(title, expected):
    assert mod.classify(title) == expected


def meta(*types):
    return json.dumps([{"dependencyName": f"d{i}", "updateType": t} for i, t in enumerate(types)])


@pytest.mark.parametrize(
    "raw,expected",
    [
        (meta("version-update:semver-patch"), "patch"),
        (meta("version-update:semver-minor"), "minor"),
        (meta("version-update:semver-patch", "version-update:semver-minor"), "minor"),
        (meta("version-update:semver-minor", "version-update:semver-major"), "major"),
        (meta("version-update:semver-patch", "something-new"), "major"),
        ("[]", "major"),
        ("not json", "major"),
        ('{"a": 1}', "major"),
        ("[1]", "major"),
    ],
)
def test_classify_metadata(raw, expected):
    assert mod.classify("Bump the x group with 2 updates", raw) == expected


def test_metadata_beats_title_and_empty_falls_back():
    assert mod.classify("Bump foo from 1.0.0 to 2.0.0", meta("version-update:semver-minor")) == "minor"
    assert mod.classify("Bump foo from 1.0.0 to 1.0.1", "  ") == "patch"
