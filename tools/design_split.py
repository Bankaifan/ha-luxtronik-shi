"""Create the implementation issues of a merged design by script (no model), issue #417.

  python3 tools/design_split.py check [ROOT]          parse section 8 of every design numbered 0016 or higher (make check)
  python3 tools/design_split.py run BEFORE AFTER      push to main: split every design file added in BEFORE..AFTER

Section 8 of a design is a fixed format, one block per step (see docs/design/README.md):

    ### Step 2: Title of the step
    Files: `tools/a.py`, `tests/test_a.py`
    Acceptance: one line
    Depends on: 1            (optional, earlier step numbers, comma separated)

`run` creates one issue per step: body `Design: <path>`, `Depends on: #<n>[, #<m>]` (step numbers mapped to the issue
numbers), then the slip (`Files:` and `Acceptance:`). The label is the prio of the source issue (the issue the design PR
names with `Refs #N`), which also loses `agent:dev` and `needs-human`. The source issue body gets one `Depends on:` line
with the final steps (no other step depends on them), so the dispatcher does not start it again (#544); an existing
`Depends on:` line is replaced. Idempotent: a step whose title already exists in an issue with the same `Design:` line is
reused, not created again. Text is untrusted: only these lines are parsed. Needs gh (GH_TOKEN, GH_REPO) and git.
"""
import json
import os
import pathlib
import re
import sys

import prefilter

FIRST_PARSED = 16  # older designs use a table in section 8 and are not split by script
_DESIGN_PATH = re.compile(r"^docs/design/(\d{4})-[a-z0-9-]+\.md$")
_STEP = re.compile(r"^### Step (\d+): (\S.*?)\s*$")
_SECTION = re.compile(r"^## 8\. ", re.MULTILINE)
_NEXT = re.compile(r"^## ", re.MULTILINE)
_FIELD = re.compile(r"^(Files|Acceptance|Depends on): *(\S.*?)\s*$")
_PRIOS = ("prio:1", "prio:2", "prio:3")


class DesignError(ValueError):
    pass


def parse_section8(text):
    """List of {"step", "title", "files", "acceptance", "depends"} of section 8 of TEXT; DesignError when it does not parse."""
    m = _SECTION.search(text)
    if not m:
        raise DesignError("no section '## 8. ...'")
    rest = text[m.end():]
    nxt = _NEXT.search(rest)
    lines = (rest[:nxt.start()] if nxt else rest).splitlines()
    steps = []
    for line in lines:
        s = _STEP.match(line)
        if s:
            steps.append({"step": int(s.group(1)), "title": s.group(2), "fields": {}})
            continue
        f = _FIELD.match(line)
        if f and steps:
            if f.group(1) in steps[-1]["fields"]:
                raise DesignError(f"step {steps[-1]['step']}: duplicate '{f.group(1)}:' line")
            steps[-1]["fields"][f.group(1)] = f.group(2)
    if not steps:
        raise DesignError("section 8 has no '### Step N: title' block")
    out = []
    for i, st in enumerate(steps, 1):
        n, fields = st["step"], st["fields"]
        if n != i:
            raise DesignError(f"step numbers must run 1, 2, 3, ...: found {n} at position {i}")
        for need in ("Files", "Acceptance"):
            if need not in fields:
                raise DesignError(f"step {n}: missing '{need}:' line")
        if any(o["title"] == st["title"] for o in out):
            raise DesignError(f"step {n}: duplicate step title '{st['title']}'")
        depends = []
        if "Depends on" in fields:
            if not re.fullmatch(r"\d+(?:, *\d+)*", fields["Depends on"]):
                raise DesignError(f"step {n}: 'Depends on:' must be step numbers like '1, 2'")
            depends = [int(d) for d in re.findall(r"\d+", fields["Depends on"])]
            if any(d >= n for d in depends):
                raise DesignError(f"step {n}: 'Depends on:' names a step that is not earlier")
        out.append({"step": n, "title": st["title"], "files": fields["Files"],
                    "acceptance": fields["Acceptance"], "depends": depends})
    return out


def check(root):
    """Error lines for every design numbered FIRST_PARSED or higher under ROOT whose section 8 does not parse."""
    errs = []
    for p in sorted((root / "docs" / "design").glob("[0-9][0-9][0-9][0-9]-*.md")):
        if int(p.name[:4]) < FIRST_PARSED:
            continue
        try:
            parse_section8(p.read_text(encoding="utf-8"))
        except DesignError as e:
            errs.append(f"{p.relative_to(root)}: section 8: {e}")
    return errs


def _issue_number(url):
    m = re.search(r"/(\d+)\s*$", url)
    if not m:
        raise DesignError(f"cannot read the issue number from gh output: {url!r}")
    return int(m.group(1))


def existing(gh, design):
    """{title: number} of the issues (any state) whose body has the line `Design: DESIGN`."""
    found = json.loads(gh("issue", "list", "--state", "all", "--limit", "200", "--search", f'"Design: {design}" in:body',
                          "--json", "number,title,body"))
    return {i["title"]: i["number"] for i in found if f"\nDesign: {design}\n" in f"\n{i['body']}\n"}


def _final_steps(steps):
    """Step numbers that no other step depends on, in step order."""
    needed = {d for st in steps for d in st["depends"]}
    return [st["step"] for st in steps if st["step"] not in needed]


def _with_depends(body, line):
    """BODY with its `Depends on:` lines replaced by LINE (kept at the first one's place), or LINE appended."""
    out = []
    placed = False
    for text in body.splitlines():
        if text.startswith("Depends on:"):
            if not placed:
                out.append(line)
                placed = True
            continue
        out.append(text)
    if not placed:
        out.append(line)
    return "\n".join(out)


def split(design, text, source, gh=prefilter.gh):
    """Create the issues of the design file DESIGN (TEXT is its content); returns {step: issue number}.
    SOURCE is the source issue number or None."""
    steps = parse_section8(text)
    prio = []
    view = {}
    if source:
        view = json.loads(gh("issue", "view", str(source), "--json", "labels,body"))
        prio = [lab["name"] for lab in view["labels"] if lab["name"] in _PRIOS][:1]
    have = existing(gh, design)
    numbers = {}
    for st in steps:
        if st["title"] in have:
            numbers[st["step"]] = have[st["title"]]
            continue
        body = [f"Design: {design}"]
        if st["depends"]:
            body.append("Depends on: " + ", ".join(f"#{numbers[d]}" for d in st["depends"]))
        body += ["", f"Files: {st['files']}", f"Acceptance: {st['acceptance']}"]
        args = ["issue", "create", "--title", st["title"], "--body", "\n".join(body)]
        for lab in prio:
            args += ["--label", lab]
        numbers[st["step"]] = _issue_number(gh(*args))
        print(f"step {st['step']}: created #{numbers[st['step']]}")
    if source:
        body = view.get("body") or ""
        line = "Depends on: " + ", ".join(f"#{numbers[s]}" for s in _final_steps(steps))
        new = _with_depends(body, line)
        if new != body.rstrip("\n"):
            gh("issue", "edit", str(source), "--body", new)
        gh("issue", "edit", str(source), "--remove-label", "agent:dev", "--remove-label", "needs-human")
    return numbers


def source_issue(design, before, after, gh=prefilter.gh, git=prefilter.git):
    """The issue the merged design PR names with `Refs #N` / `Closes #N`, else None."""
    sha = git("log", "--diff-filter=A", "--format=%H", f"{before}..{after}", "--", design).splitlines()
    if not sha:
        return None
    pulls = json.loads(gh("api", f"repos/{os.environ['GH_REPO']}/commits/{sha[-1]}/pulls"))
    for p in pulls:
        found = sorted(prefilter.closing_issues(p.get("body")))
        if found:
            return found[0]
    return None


def run(before, after, root, gh=prefilter.gh, git=prefilter.git):
    """Split every design file added in BEFORE..AFTER; returns 1 when one of them does not parse."""
    names = git("diff", "--diff-filter=A", "--name-only", before, after, "--", "docs/design/").splitlines()
    rc = 0
    for design in names:
        m = _DESIGN_PATH.match(design)
        if not m or int(m.group(1)) < FIRST_PARSED:
            continue
        try:
            text = (root / design).read_text(encoding="utf-8")
            split(design, text, source_issue(design, before, after, gh, git), gh)
        except DesignError as e:
            print(f"{design}: {e}", file=sys.stderr)
            rc = 1
    return rc


def main(argv) -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    if argv and argv[0] == "check" and len(argv) <= 2:
        errs = check(pathlib.Path(argv[1]) if len(argv) == 2 else root)
        for e in errs:
            print(f"design_split: {e}")
        if not errs:
            print("design_split: ok")
        return 1 if errs else 0
    if argv and argv[0] == "run" and len(argv) == 3:
        return run(argv[1], argv[2], root)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
