"""gh helper: reads retry transient failures, writes never, the final error names stderr."""
import subprocess

import ghcall
import pytest


def fake_run(results, calls):
    def run(cmd, **kw):
        calls.append(cmd)
        r = results.pop(0)
        if isinstance(r, str):
            return subprocess.CompletedProcess(cmd, 0, stdout=r, stderr="")
        raise subprocess.CalledProcessError(1, cmd, output="", stderr=r["err"])

    return run


def test_read_fails_once_then_succeeds(monkeypatch):
    calls, waits = [], []
    monkeypatch.setattr(ghcall.subprocess, "run", fake_run([{"err": "HTTP 502"}, "ok"], calls))
    assert ghcall.gh("api", "repos/o/r/actions/runs/1", sleep=waits.append) == "ok"
    assert len(calls) == 2 and waits == [2]


def test_read_gives_up_after_two_retries(monkeypatch):
    calls, waits = [], []
    errs = [{"err": "boom"}] * 2 + [{"err": "x" * 400 + "LAST"}]
    monkeypatch.setattr(ghcall.subprocess, "run", fake_run(errs, calls))
    with pytest.raises(subprocess.CalledProcessError) as e:
        ghcall.gh("pr", "diff", "546", sleep=waits.append)
    assert len(calls) == 3 and waits == [2, 5]
    assert str(e.value).endswith("LAST") and "x" * 296 + "LAST" in str(e.value) and "x" * 297 not in str(e.value)


@pytest.mark.parametrize("args", [
    ("api", "-X", "POST", "repos/o/r/issues"),
    ("api", "--method", "PATCH", "x"),
    ("api", "x", "-f", "a=b"),
    ("api", "x", "--input", "-"),
    ("pr", "comment", "1", "--body", "hi"),
    ("issue", "edit", "1"),
])
def test_write_is_not_repeated(monkeypatch, args):
    calls = []
    monkeypatch.setattr(ghcall.subprocess, "run", fake_run([{"err": "nope"}, "late"], calls))
    with pytest.raises(subprocess.CalledProcessError) as e:
        ghcall.gh(*args, sleep=lambda s: None)
    assert len(calls) == 1 and "nope" in str(e.value)


@pytest.mark.parametrize("args", [
    ("api", "x"), ("api", "-X", "GET", "x"), ("pr", "view", "1"), ("pr", "list"), ("issue", "list"),
    ("run", "view", "1"), ("label", "list"),
])
def test_reads_are_recognised(args):
    assert ghcall.is_read(args)


def test_rate_limit_is_not_retried_and_is_named(monkeypatch):
    """#511: waiting seconds does not bring the hourly budget back; the error says what happened."""
    calls, waits = [], []
    err = "gh: API rate limit exceeded for installation ID 1. If you reach out to GitHub Support " + "x" * 300
    monkeypatch.setattr(ghcall.subprocess, "run", fake_run([{"err": err}], calls))
    with pytest.raises(ghcall.GhError) as e:
        ghcall.gh("api", "repos/o/r/actions/runs", sleep=waits.append)
    assert len(calls) == 1 and not waits and "GitHub API rate limit exceeded." in str(e.value)

