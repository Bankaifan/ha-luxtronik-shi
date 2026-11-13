import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location("conftest_under_test", ROOT / "tests" / "agent" / "conftest.py")
conf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conf)


class _Item:
    def __init__(self, template_only):
        self.template_only = template_only
        self.added = []

    def get_closest_marker(self, name):
        return object() if self.template_only and name == "template_only" else None

    def add_marker(self, mark):
        self.added.append(mark)


def test_slow_marker_is_registered(pytestconfig):
    markers = pytestconfig.getini("markers")
    assert any(line.split(":", 1)[0].strip() == "slow" for line in markers)


def test_template_only_marker_is_registered(pytestconfig):
    markers = pytestconfig.getini("markers")
    assert any(line.split(":", 1)[0].strip() == "template_only" for line in markers)


def test_downstream_is_marked_by_template_json(tmp_path):
    assert not conf.is_downstream(tmp_path)
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents" / "template.json").write_text("{}")
    assert conf.is_downstream(tmp_path)


def test_template_only_tests_are_skipped_only_downstream(monkeypatch):
    items = [_Item(True), _Item(False)]
    monkeypatch.setattr(conf, "is_downstream", lambda root=conf.ROOT: True)
    conf.pytest_collection_modifyitems(None, items)
    assert len(items[0].added) == 1 and items[0].added[0].name == "skip"
    assert items[1].added == []

    items = [_Item(True)]
    monkeypatch.setattr(conf, "is_downstream", lambda root=conf.ROOT: False)
    conf.pytest_collection_modifyitems(None, items)
    assert items[0].added == []
