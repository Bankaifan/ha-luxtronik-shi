def test_slow_marker_is_registered(pytestconfig):
    markers = pytestconfig.getini("markers")
    assert any(line.split(":", 1)[0].strip() == "slow" for line in markers)
