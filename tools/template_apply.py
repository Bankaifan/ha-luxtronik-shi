"""Apply a template sync to the working tree (design 0014, section 4.1: plan, path guard, three-way merge, write, delete,
commit) and materialize the conflicted files for the developer (4.3).

Pure functions plus `git merge-file` and `git` calls. Nothing here talks to GitHub: the caller passes the template texts in
(read through the contents API). Every write or delete goes through check_path, so only relative, managed paths
inside the repo are touched. This module does not import template_sync (template_sync imports it, step 3).
"""
import pathlib
import subprocess
import tempfile

WRITE_STATUS = ("added", "modified", "renamed")  # take the file from the template at the target SHA
DELETE_STATUS = ("removed", "renamed-from")  # remove the downstream file


class PathRefused(Exception):
    """A template path that the apply run must not write or delete."""


def plan(changed, overrides):
    """Split changed entries into (clean, overridden); same rule as template_sync.split_overrides."""
    why = {o["path"]: o.get("why", "") for o in overrides}
    clean = [c for c in changed if c["path"] not in why]
    overridden = [{**c, "why": why[c["path"]]} for c in changed if c["path"] in why]
    return clean, overridden


def check_path(path, managed):
    """Return path when it is a relative managed path without a `..` segment; otherwise raise PathRefused."""
    if not isinstance(path, str) or not path or "\\" in path:
        raise PathRefused(f"bad path: {path!r}")
    posix = pathlib.PurePosixPath(path)
    if posix.is_absolute() or ".." in posix.parts:
        raise PathRefused(f"path leaves the repo: {path}")
    if not any(path.startswith(m) if m.endswith("/") else path == m for m in managed):
        raise PathRefused(f"path is not managed: {path}")
    return path


def _inside(root, path, managed):
    """Target of a checked path under root; refuses a symlink that resolves outside the repo."""
    check_path(path, managed)
    target = pathlib.Path(root, path)
    if not target.resolve().is_relative_to(pathlib.Path(root).resolve()):
        raise PathRefused(f"path resolves outside the repo: {path}")
    return target


def _read_text(target):
    """UTF-8 text of an existing file; None when it is missing, a directory or not UTF-8."""
    if not target.is_file():
        return None
    try:
        return target.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return None


def three_way(ours, base, theirs):
    """Three-way merge of texts with `git merge-file -p` (design 0014, 3 D).

    Returns ("clean", merged) or ("conflict", None). A missing side (None: no base when the file is new in the template,
    or no theirs/ours text when it is absent at that ref) and NUL bytes are conflicts; so is any git error (exit code
    not 0). The merged text is returned only when clean, so a conflict marker can never reach a file.
    """
    if any(text is None for text in (ours, base, theirs)) or any("\0" in text for text in (ours, base, theirs)):
        return "conflict", None
    with tempfile.TemporaryDirectory() as tmp:
        names = []
        for name, text in (("ours", ours), ("base", base), ("theirs", theirs)):
            path = pathlib.Path(tmp, name)
            path.write_bytes(text.encode("utf-8"))
            names.append(str(path))
        proc = subprocess.run(["git", "merge-file", "-p", *names], capture_output=True, check=False)
    if proc.returncode != 0:
        return "conflict", None
    try:
        return "clean", proc.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return "conflict", None


def write_file(root, path, text, managed):
    """Write a managed file under root (creates parent directories), bytes exactly as given."""
    target = _inside(root, path, managed)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(text.encode("utf-8"))


def delete_file(root, path, managed):
    """Delete a managed file under root; False when it was already gone."""
    target = _inside(root, path, managed)
    if not target.is_file() and not target.is_symlink():
        return False
    target.unlink()
    return True


def apply_clean(root, clean, read_template, managed):
    """Write added/modified/renamed clean files and delete removed/renamed-from ones.

    read_template(path) returns the template text at the target SHA. All paths and statuses are checked before the
    first write, so a refused entry leaves the tree as it was. Returns {"written": [...], "deleted": [...]}.
    """
    for c in clean:
        check_path(c["path"], managed)
        if c["status"] not in WRITE_STATUS + DELETE_STATUS:
            raise ValueError(f"unknown status {c['status']!r} for {c['path']}")
    written, deleted = [], []
    for c in clean:
        if c["status"] in WRITE_STATUS:
            write_file(root, c["path"], read_template(c["path"]), managed)
            written.append(c["path"])
        elif delete_file(root, c["path"], managed):
            deleted.append(c["path"])
    return {"written": written, "deleted": deleted}


def _texts(root, o, base_of, theirs_of, managed):
    """(ours, base, theirs): the downstream text (None when absent) and the template texts at synced_sha and at the target."""
    path = o["path"]
    return _read_text(_inside(root, path, managed)), base_of(path), theirs_of(path)


def _verdict(o, ours, base, theirs):
    """("clean", merged) or ("conflict", None). Only a modified file with all three texts can merge."""
    if o["status"] != "modified" or ours is None:
        return "conflict", None
    return three_way(ours, base, theirs)


def merge_overridden(root, overridden, base_of, theirs_of, managed):
    """Three-way merge of overridden files: ours = the downstream file, base = template at synced_sha, theirs = template
    at the target SHA. A clean result is written; anything else leaves the downstream file untouched and is listed as
    conflicted (design 0014, 4.1 step 3).

    base_of(path) and theirs_of(path) return text, or None when the file is absent at that ref. Only a modified file is
    merged; removed, renamed and added ones are conflicts (no base to merge against). Returns
    {"merged": [...], "conflicted": [...]}.
    """
    for o in overridden:
        check_path(o["path"], managed)
    merged, conflicted = [], []
    for o in overridden:
        path = o["path"]
        status, text = _verdict(o, *_texts(root, o, base_of, theirs_of, managed))
        if status == "clean":
            write_file(root, path, text, managed)
            merged.append(path)
        else:
            conflicted.append(path)
    return {"merged": merged, "conflicted": conflicted}


def materialize(root, overridden, base_of, theirs_of, managed, out_dir):
    """Write ours, base and theirs of every conflicted overridden file under out_dir (never into the tree), so the
    developer can merge by hand (design 0014, 3 H). A side that is absent at its ref is not written. Returns the
    conflicted paths."""
    for o in overridden:
        check_path(o["path"], managed)
    conflicted = []
    for o in overridden:
        path = o["path"]
        ours, base, theirs = _texts(root, o, base_of, theirs_of, managed)
        if _verdict(o, ours, base, theirs)[0] == "clean":
            continue
        conflicted.append(path)
        for suffix, text in (("ours", ours), ("base", base), ("theirs", theirs)):
            if text is not None:
                target = pathlib.Path(out_dir, f"{path}.{suffix}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(text.encode("utf-8"))
    return conflicted


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


def commit_paths(root, paths, branch, message, name, email):
    """Put exactly `paths` (added, changed or deleted) into one commit on `branch`, which `switch -C` resets to HEAD.

    The identity is given per command: no git config is written and no trailer is added. Returns the new SHA, or None
    when the paths hold no change (nothing to commit).
    """
    if not paths:
        raise ValueError("no paths to commit")
    git(root, "switch", "-q", "-C", branch)
    git(root, "add", "-A", "--", *paths)
    if not git(root, "diff", "--cached", "--name-only").strip():
        return None
    git(root, "-c", f"user.name={name}", "-c", f"user.email={email}", "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD").strip()
