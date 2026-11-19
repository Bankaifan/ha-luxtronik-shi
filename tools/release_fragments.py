"""Assign VERSION and fold changelog fragments into CHANGELOG.md (issue #468, design 0013 option A). No model.

Usage: release_fragments.py [ROOT]   (ROOT default: the current directory; run on main, one writer)
A PR adds `changelog.d/<issue>.md`: one or more changelog lines and an optional `step: x` or `step: y` line (default y).
One run is one release and one version step, however many fragments it folds: (m+1).0 when a fragment says `step: x`,
else m.(n+1). All lines, in issue-number order, go into one `## [x.y] - date` section above the newest released heading
in CHANGELOG.md; the fragments are deleted and VERSION is rewritten. Prints one line per fragment, then one
`note: <line>` per line meant for the owner (the release PR body, tools/train.py). A line `internal: <text>` is a change
users do not see: it goes into CHANGELOG.md without the prefix and is no note.
Nothing to do (no fragments): no change, exit 0. A malformed fragment stops the run before any file is written (exit 1).
"""
import datetime
import pathlib
import re
import sys

VERSION_FILE = "VERSION"
CHANGELOG = "CHANGELOG.md"
FRAGMENT_DIR = "changelog.d"
FRAGMENT_NAME = re.compile(r"[0-9]+\.md")
STEP = re.compile(r"step:\s*([xy])\s*")
INTERNAL = "- internal:"
HEADING = re.compile(r"^## \[([^\]]+)\](.*)$")


class Refused(Exception):
    """A fragment or file cannot be released; the message says why."""


def parse_version(text):
    m = re.fullmatch(r"([0-9]+)\.([0-9]+)", (text or "").removesuffix("\n"), flags=re.ASCII)
    if not m:
        raise Refused(f"VERSION {(text or '').strip()!r} is not x.y (digits, one dot, no prefix)")
    return int(m.group(1)), int(m.group(2))


def next_version(current, step):
    """`x.y` text after one step: x gives (x+1).0, y gives x.(y+1)."""
    x, y = parse_version(current)
    return f"{x + 1}.0" if step == "x" else f"{x}.{y + 1}"


def parse_fragment(name, text):
    """(step, bullet lines) of a fragment. Refused when it holds no changelog line or two step lines."""
    step, bullets = None, []
    for line in text.split("\n"):
        line = line.rstrip()
        if not line.strip():
            continue
        m = STEP.fullmatch(line.strip())
        if m:
            if step:
                raise Refused(f"{name}: more than one step line")
            step = m.group(1)
        elif re.match(r"step:", line.strip()):
            raise Refused(f"{name}: step line must be `step: x` or `step: y`")
        else:
            bullets.append(line if line.startswith("- ") else f"- {line}")
    if not bullets:
        raise Refused(f"{name}: no changelog line")
    return step or "y", bullets


def add_section(changelog, version, date, bullets):
    """CHANGELOG.md text with a `## [version] - date` section above the newest released heading."""
    out = changelog.split("\n")
    if any((m := HEADING.match(line)) and m.group(1) == version for line in out):
        raise Refused(f"CHANGELOG.md already has a [{version}] heading")
    idx = next(
        (i for i, line in enumerate(out) if (m := HEADING.match(line)) and m.group(1).lower() != "unreleased"),
        None,
    )
    block = [f"## [{version}] - {date}", *bullets, ""]
    if idx is None:  # no released heading yet: append after the last line
        while out and not out[-1].strip():
            out.pop()
        return "\n".join(out + [""] + block)
    return "\n".join(out[:idx] + block + out[idx:])


def fragments(root):
    """Fragment files of changelog.d in issue-number order."""
    d = root / FRAGMENT_DIR
    if not d.is_dir():
        return []
    return sorted((p for p in d.iterdir() if FRAGMENT_NAME.fullmatch(p.name)), key=lambda p: int(p.stem))


def release(root, today, notes=None):
    """Release every fragment under `root` as one version; returns [(version, fragment name)]. Writes only when all
    fragments parse. `notes`, if a list, receives the user-facing lines."""
    root = pathlib.Path(root)
    files = fragments(root)
    if not files:
        return []
    version_path, changelog_path = root / VERSION_FILE, root / CHANGELOG
    if not version_path.is_file() or not changelog_path.is_file():
        raise Refused("VERSION or CHANGELOG.md is missing")
    version = version_path.read_text(encoding="utf-8").strip()
    parse_version(version)
    changelog = changelog_path.read_text(encoding="utf-8")
    parsed = [parse_fragment(p.name, p.read_text(encoding="utf-8")) for p in files]
    version = next_version(version, "x" if any(step == "x" for step, _ in parsed) else "y")
    bullets = [b for _, bs in parsed for b in bs]
    changelog = add_section(changelog, version, today, [f"- {b[len(INTERNAL):].lstrip()}" if b.startswith(INTERNAL) else b for b in bullets])
    done = [(version, p.name) for p in files]
    if notes is not None:
        notes.extend(b for b in bullets if not b.startswith(INTERNAL))
    version_path.write_text(f"{version}\n", encoding="utf-8")
    changelog_path.write_text(changelog, encoding="utf-8")
    for p in files:
        p.unlink()
    return done


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = pathlib.Path(args[0]) if args else pathlib.Path(".")
    try:
        notes = []
        done = release(root, datetime.datetime.now(datetime.UTC).date().isoformat(), notes)
    except (Refused, OSError) as e:
        print(f"release_fragments: refused: {e}")
        return 1
    for version, name in done:
        print(f"release_fragments: {name} -> {version}")
    for note in notes:
        print(f"note: {note}")
    if not done:
        print("release_fragments: no fragments")
    return 0


if __name__ == "__main__":
    sys.exit(main())
