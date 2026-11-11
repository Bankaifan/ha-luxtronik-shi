"""Cap the size of the instruction files agents load (issue #407).

Every agent run loads AGENTS.md plus its role file, so their growth is capped. The caps live in docs/budgets.json
(bytes per file, plus a total). Shrinking never fails. Fails: a file over its cap, a file without a budget entry,
the total over its cap. Raising a cap is an edit of docs/budgets.json, which shows up in the diff.
"""
import json
import pathlib
import sys

BUDGETS = "docs/budgets.json"


def instruction_files(root):
    """Repo-relative paths of AGENTS.md and every .agents/roles/*.md, sorted."""
    roles = sorted(f".agents/roles/{p.name}" for p in (root / ".agents" / "roles").glob("*.md"))
    return ["AGENTS.md", *roles]


def load_budgets(root):
    """{"files": {path: bytes}, "total": bytes} from docs/budgets.json; ValueError when malformed."""
    data = json.loads((root / BUDGETS).read_text(encoding="utf-8"))
    ok = (
        isinstance(data, dict)
        and isinstance(data.get("files"), dict)
        and all(isinstance(v, int) for v in data["files"].values())
        and isinstance(data.get("total"), int)
    )
    if not ok:
        raise ValueError(f'{BUDGETS}: expected {{"files": {{path: bytes}}, "total": bytes}}')
    return data


def errors(sizes, budgets):
    """Error lines for {path: bytes} against the budgets; empty list means fine."""
    out = []
    caps = budgets["files"]
    for name, size in sizes.items():
        if name not in caps:
            out.append(f"{name} has no budget entry, add it to {BUDGETS}")
        elif size > caps[name]:
            out.append(f"{name} is {size} bytes, over its cap of {caps[name]} bytes")
    total = sum(sizes.values())
    if total > budgets["total"]:
        out.append(f"instruction files total {total} bytes, over the cap of {budgets['total']} bytes")
    return out


def main(root=None) -> int:
    root = pathlib.Path(root) if root is not None else pathlib.Path(__file__).resolve().parent.parent.parent
    try:
        budgets = load_budgets(root)
        sizes = {name: (root / name).stat().st_size for name in instruction_files(root)}
    except (OSError, ValueError) as e:
        print(f"check_budget: cannot run: {e}", file=sys.stderr)
        return 2
    errs = errors(sizes, budgets)
    for e in errs:
        print(f"check_budget: {e}")
    if not errs:
        print(f"check_budget: ok ({len(sizes)} files, {sum(sizes.values())} of {budgets['total']} bytes)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
