"""template_sync apply and materialize on a real git fixture (design 0014, sections 4.1, 4.3 and 6).

Acceptance 1: 3 clean files, 1 new file, 1 overridden file that merges, 1 overridden file that conflicts. apply makes one
commit with the five, leaves synced_sha alone and names the sixth file in the PR body; materialize writes its three versions.
"""
import importlib.util
import json
import pathlib
import subprocess

_TOOLS = pathlib.Path(__file__).parent.parent.parent / "tools"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ts = _load("template_sync")
mg = _load("managed_guard")

SYNCED, MAIN = "a" * 40, "b" * 40
AUTHOR = "Daniel <476059+Bankaifan@users.noreply.github.com>"
PROJECT = {  # the project's files: the overridden ones are edited on purpose
    "tools/a.py": "one\ntwo\nthree\n",
    "tools/gone.py": "bye\n",
    "tools/over_ok.py": "mine 1\nb\nc\n",
    "tools/over_conflict.py": "mine\n",
}
TEMPLATE = {  # (ref, path) -> text; a missing key is a file absent at that ref
    (SYNCED, "tools/a.py"): "one\ntwo\nthree\n",
    (SYNCED, "tools/gone.py"): "bye\n",
    (SYNCED, "tools/over_ok.py"): "1\nb\nc\n",
    (SYNCED, "tools/over_conflict.py"): "x\n",
    (MAIN, "tools/a.py"): "one\nTWO\nthree\n",
    (MAIN, "tools/b.py"): "new b\n",
    (MAIN, "tools/c.py"): "new c\n",
    (MAIN, "tools/over_ok.py"): "1\nb\nC\n",
    (MAIN, "tools/over_conflict.py"): "theirs\n",
    (MAIN, "VERSION"): "1.1\n",
}
COMPARE = {"files": [
    {"filename": "tools/a.py", "status": "modified"},
    {"filename": "tools/gone.py", "status": "removed"},
    {"filename": "tools/b.py", "status": "added"},
    {"filename": "tools/c.py", "status": "added"},
    {"filename": "tools/over_ok.py", "status": "modified"},
    {"filename": "tools/over_conflict.py", "status": "modified"},
    {"filename": "README.md", "status": "modified"},  # not managed: ignored
]}
FIVE = ["tools/a.py", "tools/b.py", "tools/c.py", "tools/gone.py", "tools/over_ok.py"]


def _config(overrides=("tools/over_ok.py", "tools/over_conflict.py")):
    return {"template": "o/t", "synced_sha": SYNCED, "synced_version": "1.0", "managed": ["tools/", "AGENTS.md"],
            "overrides": [{"path": p, "why": "local"} for p in overrides]}


def _reader(extra=None):
    table = {**TEMPLATE, **(extra or {})}
    return lambda ref, path: table.get((ref, path))


def _without(path):
    return {"files": [f for f in COMPARE["files"] if f["filename"] != path]}


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


def _project(tmp_path, cfg=None):
    root = tmp_path / "project"
    for path, text in PROJECT.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    (root / ".agents").mkdir()
    (root / ".agents" / "template.json").write_text(json.dumps(cfg or _config(), indent=2) + "\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "-q", "-m", "project")
    return root


def _cfg(root):
    return ts.parse_config((root / ".agents" / "template.json").read_text())


def _committed(root):
    return sorted(_git(root, "show", "--name-only", "--format=", "HEAD").split())


def test_apply_one_commit_names_the_conflict_file_and_keeps_synced_sha(tmp_path):
    root = _project(tmp_path)
    result = ts.apply_sync(root, _cfg(root), COMPARE, MAIN, "1.1", _reader(), issue=477)
    assert result["conflicted"] == ["tools/over_conflict.py"]
    assert result["title"] == "Template sync bbbbbbb part 1"
    assert _committed(root) == FIVE  # synced_sha not bumped, so template.json is not in the commit
    assert (root / "tools" / "a.py").read_text() == "one\nTWO\nthree\n"
    assert not (root / "tools" / "gone.py").exists()
    assert (root / "tools" / "b.py").read_text() == "new b\n"
    assert (root / "tools" / "over_ok.py").read_text() == "mine 1\nb\nC\n"
    assert (root / "tools" / "over_conflict.py").read_text() == "mine\n"  # left alone, no markers
    assert json.loads((root / ".agents" / "template.json").read_text())["synced_sha"] == SYNCED
    assert "`tools/over_conflict.py`" in result["body"] and "Refs #477" in result["body"]
    assert "Closes" not in result["body"]
    assert _git(root, "log", "-1", "--format=%an <%ae>").strip() == AUTHOR
    assert "co-authored-by" not in _git(root, "log", "-1", "--format=%B").lower()


def test_apply_without_conflicts_bumps_synced_and_closes_the_issue(tmp_path):
    root = _project(tmp_path)
    compare = _without("tools/over_conflict.py")
    managed_json = '{"managed": ["tools/", "docs/x/"]}'
    result = ts.apply_sync(root, _cfg(root), compare, MAIN, "1.1", _reader({(MAIN, ".agents/managed.json"): managed_json}),
                           issue=477)
    assert result["conflicted"] == [] and result["title"] == "Template sync 1.1"
    assert result["managed_added"] == ["docs/x/"]
    cfg = json.loads((root / ".agents" / "template.json").read_text())
    assert (cfg["synced_sha"], cfg["synced_version"], cfg["managed"]) == (MAIN, "1.1", ["tools/", "AGENTS.md", "docs/x/"])
    assert result["body"].splitlines()[-1] == "Closes #477"
    assert _committed(root) == sorted(FIVE + [".agents/template.json"])


def test_materialize_writes_three_versions_of_the_conflict_file_only(tmp_path):
    root = _project(tmp_path)
    out = root / ".template"
    got = ts.materialize_sync(root, _cfg(root), COMPARE, MAIN, _reader(), out)
    assert got == ["tools/over_conflict.py"]
    assert (out / "tools" / "over_conflict.py.ours").read_text() == "mine\n"
    assert (out / "tools" / "over_conflict.py.base").read_text() == "x\n"
    assert (out / "tools" / "over_conflict.py.theirs").read_text() == "theirs\n"
    assert not (out / "tools" / "over_ok.py.ours").exists()
    assert (root / "tools" / "over_conflict.py").read_text() == "mine\n"


def test_conflict_pr_passes_the_guard_and_a_plain_pr_with_the_same_files_does_not(tmp_path):
    root = _project(tmp_path)
    result = ts.apply_sync(root, _cfg(root), COMPARE, MAIN, "1.1", _reader(), issue=477)
    cfg = {"template": "o/t", "managed": ["tools/", "AGENTS.md"],
           "overrides": [{"path": "tools/over_ok.py"}, {"path": "tools/over_conflict.py"}]}
    assert mg.pr_errors(cfg, "o/project", result["title"], _committed(root)) == []
    assert mg.pr_errors(cfg, "o/project", "Template sync 1.1", _committed(root)) != []


def _cli(monkeypatch, compare=COMPARE, reader=None):
    """Run the command functions on the fixture: gh answers the compare API, template_reader reads the fixture table."""
    calls = []

    def fake_gh(*args):
        calls.append(args)
        return json.dumps(compare)

    monkeypatch.setattr(ts, "gh", fake_gh)
    monkeypatch.setattr(ts, "template_reader", lambda template: reader or _reader())
    return calls


def test_cli_apply_writes_the_body_file_and_prints_the_part_1_title(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    calls = _cli(monkeypatch)
    body = tmp_path / "body.md"
    assert ts.cmd_apply(["--root", str(root), "--sha", MAIN, "--body-file", str(body), "--issue", "477"]) == 0
    assert calls == [("api", f"repos/o/t/compare/{SYNCED}...{MAIN}")]
    assert body.read_text() == ("Template 1.1 (bbbbbbb): 3 written, 1 deleted, 1 overridden merged.\n"
                                "Developer merges by hand, synced_sha not set: `tools/over_conflict.py`\n"
                                "Refs #477\n")
    assert capsys.readouterr().out == "Template sync bbbbbbb part 1\n"
    assert _git(root, "rev-list", "--count", "HEAD").strip() == "2"


def test_cli_apply_refused_path_exits_1_and_writes_nothing(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    _cli(monkeypatch, compare={"files": [{"filename": "tools/../evil.py", "status": "added"}]})
    body = tmp_path / "body.md"
    assert ts.cmd_apply(["--root", str(root), "--sha", MAIN, "--body-file", str(body)]) == 1
    assert "apply: path leaves the repo" in capsys.readouterr().err
    assert not body.exists()
    assert _git(root, "rev-list", "--count", "HEAD").strip() == "1"  # no commit


def test_cli_apply_empty_synced_sha_exits_1(tmp_path, monkeypatch, capsys):
    cfg = _config()
    cfg["synced_sha"] = ""
    root = _project(tmp_path, cfg)
    _cli(monkeypatch)
    body = tmp_path / "body.md"
    assert ts.cmd_apply(["--root", str(root), "--sha", MAIN, "--body-file", str(body)]) == 1
    assert "synced_sha is empty" in capsys.readouterr().err
    assert not body.exists()


def test_cli_apply_with_nothing_staged_writes_no_body_and_no_commit(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    _cli(monkeypatch, compare={"files": [{"filename": "tools/over_conflict.py", "status": "modified"}]})
    body = tmp_path / "body.md"
    assert ts.cmd_apply(["--root", str(root), "--sha", MAIN, "--body-file", str(body)]) == 0
    assert "nothing to commit, no PR" in capsys.readouterr().out
    assert not body.exists()
    assert _git(root, "rev-list", "--count", "HEAD").strip() == "1"


def test_cli_materialize_excludes_the_out_dir_once_across_runs(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    _cli(monkeypatch)
    for _ in range(2):
        assert ts.cmd_materialize(["--root", str(root), MAIN]) == 0
    assert capsys.readouterr().out.endswith("tools/over_conflict.py\n")
    assert (root / ".template" / "tools" / "over_conflict.py.theirs").read_text() == "theirs\n"
    assert (root / ".git" / "info" / "exclude").read_text().splitlines().count("/.template/") == 1
    assert _git(root, "status", "--porcelain") == ""  # the three versions never show up as untracked files
