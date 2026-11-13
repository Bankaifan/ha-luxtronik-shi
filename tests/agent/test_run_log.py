"""run_log: the tail of a failed run log lands in ci-failure.log, where a model run may Read it."""
import pytest
import run_log


def test_run_log_writes_the_tail(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert run_log.main(["7", "2"], gh=lambda *a: "a\nb\nc\n") == "ci-failure.log: 2 lines of run 7"
    assert (tmp_path / "ci-failure.log").read_text() == "b\nc\n"
    with pytest.raises(SystemExit):
        run_log.main(["x"])
