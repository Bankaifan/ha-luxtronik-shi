"""Execution-file helpers shared by the agent tools: read the file, mask secrets, tail it, list permission denials.

agent_guard.py imports and re-exports everything here, so existing callers keep working.
"""
import json
import re

TAIL_LINES = 15
TAIL_CHARS = 1500
MAX_DENIALS = 10
_SECRET = re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-ant-[A-Za-z0-9_-]{20,})")


def mask(text):
    """Secret-looking tokens replaced by ***."""
    return _SECRET.sub("***", text)


def has_secret(text):
    """True if the text holds a secret-looking token."""
    return bool(_SECRET.search(text))


def tail_text(text, lines=TAIL_LINES, chars=TAIL_CHARS):
    """Last lines of the execution file, secret-looking tokens masked, fences neutralized, length capped."""
    out = "\n".join(text.splitlines()[-lines:])[-chars:].replace("```", "'''")
    return _SECRET.sub("***", out)


def _records(text):
    """Execution file = JSON array of messages (or JSON lines); return every dict."""
    try:
        data = json.loads(text)
    except ValueError:
        data = []
        for line in text.splitlines():
            try:
                data.append(json.loads(line))
            except ValueError:
                pass
    return [d for d in (data if isinstance(data, list) else [data]) if isinstance(d, dict)]


def denied_calls(text, limit=MAX_DENIALS):
    """One line per denied tool call (tool + command/path) from `permission_denials`; secrets masked."""
    lines = []
    for rec in _records(text):
        for d in rec.get("permission_denials") or []:
            if not isinstance(d, dict):
                continue
            inp = d.get("tool_input")
            inp = inp if isinstance(inp, dict) else {}
            what = inp.get("command") or inp.get("file_path") or inp.get("path") or inp.get("pattern") or ""
            text_ = _SECRET.sub("***", " ".join(str(what).split()))[:150]  # mask first, then cut
            lines.append(f"{d.get('tool_name') or '?'}: {text_}".replace("`", "'"))
    more = len(lines) - limit
    return lines[:limit] + ([f"... and {more} more"] if more > 0 else [])


def count_denials(text):
    """Number of permission denials in the execution file (all of them, not only the listed ones)."""
    return sum(len([d for d in rec.get("permission_denials") or [] if isinstance(d, dict)]) for rec in _records(text))


def read_exec(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except (OSError, TypeError):
        return ""
