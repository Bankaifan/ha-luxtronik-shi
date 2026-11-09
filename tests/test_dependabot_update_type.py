import importlib.util
import pathlib

import pytest

_path = pathlib.Path(__file__).parent.parent / "tools" / "dependabot_update_type.py"
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
        ("Bump foo from abc to def", "major"),
        ("", "major"),
    ],
)
def test_classify(title, expected):
    assert mod.classify(title) == expected
