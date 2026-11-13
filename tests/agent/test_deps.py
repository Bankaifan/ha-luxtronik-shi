import deps


def test_parse_reads_numbers_from_lines_that_stand_alone():
    assert deps.parse("Design: docs/design/0001-x.md\nDepends on: #12, #13\n\nSlip") == {12, 13}
    assert deps.parse("Depends on: #7\r\ntext\r\nDepends on: #8,#9") == {7, 8, 9}


def test_parse_ignores_everything_else():
    assert deps.parse(None) == set() and deps.parse("no such line") == set()
    assert deps.parse("Depends on:") == set() and deps.parse("Depends on: ") == set()
    assert deps.parse("This Depends on: #3") == set()
    assert deps.parse("Depends on: #3 and #4") == set()
    assert deps.parse("depends on: #3") == set()
    assert deps.parse("Depends on: 3") == set()
    assert deps.parse("Depends on: #3; rm -rf /") == set()


def test_blocked_while_a_dependency_is_open():
    assert deps.blocked(20, "Depends on: #12, #13", {13, 20})
    assert not deps.blocked(20, "Depends on: #12, #13", {20, 21})
    assert not deps.blocked(20, "", {12})


def test_self_reference_is_ignored():
    assert not deps.blocked(20, "Depends on: #20", {20})
    assert deps.blocked(20, "Depends on: #20, #12", {12, 20})
