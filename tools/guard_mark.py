"""Signed marker for issues that guard scripts write (design: issue #139).

A guard script appends `<!-- guard-sig: <hex> -->` to an issue body it wrote itself: HMAC-SHA256 over title and body
with the repo secret GUARD_KEY. tools/trusted_issues.py verifies it (and the author app) before it trusts the issue.
GUARD_KEY goes to script steps only, never to a model step (tests/test_guard_mark.py checks the workflows).
Without the key nothing is signed and nothing verifies: fail closed. Only fixed script strings may be signed;
never put log, exception or model text into a signed issue.
"""
import hashlib
import hmac
import os
import re

KEY_ENV = "GUARD_KEY"
_SIG = re.compile(r"\n*<!-- guard-sig: ([0-9a-f]{64}) -->\s*$")


def _mac(title, core, key):
    msg = f"{len(title)}:{title}\n{core}".encode()
    return hmac.new(key.encode(), msg, hashlib.sha256).hexdigest()


def split(body):
    """(body without the marker, hex signature or None). Only a marker at the very end counts."""
    body = body or ""
    m = _SIG.search(body)
    return (body[:m.start()], m.group(1)) if m else (body, None)


def key_from_env(env=None):
    return (env if env is not None else os.environ).get(KEY_ENV, "")


def sign(title, body, key):
    """The body with the marker appended; unchanged if there is no key (the issue then stays untrusted)."""
    if not key:
        return body
    core = split(body)[0].strip()
    return f"{core}\n\n<!-- guard-sig: {_mac(title.strip(), core, key)} -->"


def verify(title, body, key):
    """True only for a non-empty key and a signature that matches title and body."""
    if not key:
        return False
    core, sig = split(body)
    return bool(sig) and hmac.compare_digest(sig, _mac((title or "").strip(), core.strip(), key))
