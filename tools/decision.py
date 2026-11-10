"""Decision marker: the one-line hidden comment that tells the answer receiver (design 0006) what Daniel's answer does.

Grammar: `<!-- decision: KEY=ACTION [KEY=ACTION ...] -->`, KEY is `yes`, `no` or a short option name (`a`..`z`),
ACTION is an id from ALLOWED or `label:<name>` with a name from LABELS. Everything else is refused.
This module only builds and parses; the actions themselves live in the receiver.
"""
import re

PREFIX = "decision:"
ALLOWED = ("close-pr", "close-issue", "restart-issue", "restart-recut", "fix-pr", "reapprove", "drop-block")
LABELS = ("prio:1", "prio:2", "prio:3", "approved", "auto-ok", "agent:dev", "agent:review")
# Never allowed: merge, push, tag, edits to workflows, rulesets, permissions or secrets, approving risk:security.
_MARKER = re.compile(r"<!--\s*decision:([^>]*?)\s*-->")
_KEY = re.compile(r"yes|no|[a-z]")
_MAX_PAIRS = 6


def valid_action(action):
    if action.startswith("label:"):
        return action[len("label:"):] in LABELS
    return action in ALLOWED


def build(**answers):
    """`build(yes="restart-recut", no="close-pr")` -> the marker line. ValueError on a bad key or action."""
    if not answers or len(answers) > _MAX_PAIRS:
        raise ValueError("a decision marker needs 1 to 6 answers")
    for key, action in answers.items():
        if not _KEY.fullmatch(key) or not valid_action(action):
            raise ValueError(f"bad decision {key}={action}")
    return "<!-- decision: " + " ".join(f"{k}={v}" for k, v in answers.items()) + " -->"


def parse(text):
    """The newest marker in TEXT as {key: action}, or None if there is none or it is malformed (a malformed one is never repaired)."""
    found = _MARKER.findall(text or "")
    if not found:
        return None
    parts = found[-1].split()
    result = {}
    for part in parts:
        key, sep, action = part.partition("=")
        if not sep or not _KEY.fullmatch(key) or key in result or not valid_action(action):
            return None
        result[key] = action
    if not result or len(result) > _MAX_PAIRS:
        return None
    return result


def has_marker(text):
    return parse(text) is not None


def newest(comments, trusted):
    """Marker of the newest comment by a login in TRUSTED that carries a valid one. COMMENTS: [{login, body}], oldest first.
    The author is checked by login, never by text; a marker by anyone else is ignored."""
    for c in reversed(comments):
        if c.get("login") in trusted:
            marker = parse(c.get("body"))
            if marker:
                return marker
    return None
