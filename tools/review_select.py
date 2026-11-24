"""Pick the specialist reviewers for a staged change (agent-review.yml, after the change and the delta are staged).

CLI: review_select.py [DIR]   (default `.review`)
Reads `DIR/delta.diff` if present, else `DIR/pr.diff`; writes `DIR/reviewers.txt` (one specialist per line, may be
empty) and prints the names. No model, no network: only the ADDED lines of the diff decide, per file.
  silent-failure-hunter   error handling added in a code or workflow file
  pr-test-analyzer        new logic (function or control flow) added in a non-test code file
  type-design-analyzer    a data structure defined in a non-test code file
Docs and text (`.md`, `.txt`, `.rst`, `docs/`, `changelog.d/`) pick nobody. A missing or unreadable diff is an error
(exit 1), never an empty selection. Data only, nothing is run.
"""
import os
import re
import sys

SPECIALISTS = ("silent-failure-hunter", "pr-test-analyzer", "type-design-analyzer")
DOCS = re.compile(r"(?:^|/)(?:docs|changelog\.d)/|\.(?:md|txt|rst)$", re.IGNORECASE)
CODE = re.compile(r"\.(?:py|sh|js|ts|tsx|jsx|go|rs|java|rb|kt|c|cpp|cs|php)$")
WORKFLOW = re.compile(r"^\.github/.*\.ya?ml$")
TEST = re.compile(r"(?:^|/)tests?/|(?:^|/)test_[^/]*$|(?:^|/)[^/]*(?:_test|\.test|\.spec)\.[^/]+$")
COMMENT = re.compile(r"\s*(?:#|//)")
ERRORS = re.compile(
    r"\b(?:except|catch|finally|rescue)\b|\btry:|\|\|\s*(?:true\b|echo\b|:)|2>\s*/dev/null|\bset \+e\b"
    r"|continue-on-error|always\(\)|!cancelled\(\)|fallback|check=False|\.catch\(|suppress\(", re.IGNORECASE)
LOGIC = re.compile(
    r"\b(?:def|function|func|fn) |=>|(?:^|[\s;})])(?:if|elif|else if|for|while|case|match|switch)\b")
TYPES = re.compile(
    r"\b(?:class|interface) \w|@dataclass|\b(?:TypedDict|NamedTuple|Enum)\b|\btype \w+(?:<[^=]*>)? ?="
    r"|\b(?:struct|enum|record) ")


def added_lines(diff_text):
    """[(path, line)] for every added line of a unified diff; the path is the new file of the `+++` header."""
    out, path, in_hunk = [], None, False
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            path, in_hunk = None, False
        elif not in_hunk and line.startswith("+++ "):
            name = line[4:].split("\t")[0].strip().strip('"')  # git quotes a path with special characters
            path = None if name == "/dev/null" else name.removeprefix("b/")
        elif line.startswith("@@"):
            in_hunk = True
        elif in_hunk and path and line.startswith("+"):
            out.append((path, line[1:]))
    return out


def select(diff_text):
    """Names of the specialists whose subject the added lines touch, in the order of SPECIALISTS."""
    hit = set()
    for path, line in added_lines(diff_text):
        if DOCS.search(path) or COMMENT.match(line):
            continue
        code = bool(CODE.search(path))
        if (code or WORKFLOW.search(path)) and ERRORS.search(line):
            hit.add("silent-failure-hunter")
        if code and not TEST.search(path):
            if LOGIC.search(line):
                hit.add("pr-test-analyzer")
            if TYPES.search(line):
                hit.add("type-design-analyzer")
    return [name for name in SPECIALISTS if name in hit]


def main(argv):
    if len(argv) > 2:
        print(__doc__, file=sys.stderr)
        return 2
    outdir = argv[1] if len(argv) == 2 else ".review"
    delta = os.path.join(outdir, "delta.diff")
    src = delta if os.path.exists(delta) else os.path.join(outdir, "pr.diff")
    try:
        with open(src, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        print(f"review_select: cannot read {src}: {e}", file=sys.stderr)
        return 1
    names = select(text)
    with open(os.path.join(outdir, "reviewers.txt"), "w", encoding="utf-8") as f:
        f.write("".join(f"{name}\n" for name in names))
    print(f"{os.path.basename(src)}: {', '.join(names) or 'no specialists'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
