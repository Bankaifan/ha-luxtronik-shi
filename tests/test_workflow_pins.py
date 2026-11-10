import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"

# Value of a `uses:` key, bare or quoted ("x/y@v1", 'x/y@v1', x/y@v1). The quote is not captured.
USES_RE = re.compile(r"""^\s*(?:-\s+)?uses:\s*["']?([^"'\s#]+)""")
# Third-party action or reusable workflow pinned to a full 40-char commit SHA.
PINNED_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}$")

# Documented exceptions as {"owner/repo": "reason"}. None today; every third-party action is SHA-pinned.
EXCEPTIONS: dict[str, str] = {}


def uses_refs(text):
    refs = []
    for line in text.splitlines():
        match = USES_RE.match(line)
        if match:
            refs.append(match.group(1))
    return refs


def unpinned(refs):
    bad = []
    for ref in refs:
        if ref.startswith("./"):
            continue  # local action in this repo, not third-party
        if ref.split("@", 1)[0] in EXCEPTIONS:
            continue
        if PINNED_RE.match(ref) is None:
            bad.append(ref)
    return bad


def test_workflows_are_found():
    assert list(WORKFLOWS.glob("*.yml"))


def test_every_third_party_action_is_pinned_to_sha():
    offenders = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        bad = unpinned(uses_refs(path.read_text(encoding="utf-8")))
        if bad:
            offenders[path.name] = bad
    assert offenders == {}


def test_fixture_with_quoted_and_unquoted_branch_refs_fails(tmp_path):
    wf = tmp_path / "bad.yml"
    wf.write_text(
        "jobs:\n"
        "  j:\n"
        "    steps:\n"
        '      - uses: "x/ymain"\n'
        "      - uses: x/yv1\n"
        "      - uses: 'x/y@main'\n",
        encoding="utf-8",
    )
    assert unpinned(uses_refs(wf.read_text(encoding="utf-8"))) == ["x/ymain", "x/yv1", "x/y@main"]


@pytest.mark.parametrize("line", [
    "      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1",
    '      - uses: "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"',
    "        uses: 'actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1'",
    "      - uses: ./.github/actions/local",
])
def test_pinned_or_local_refs_pass(line):
    assert unpinned(uses_refs(line)) == []
