"""Dependencies between issues: a body line `Depends on: #12, #13` holds an issue back while #12 or #13 is open.

The line stands alone (case-sensitive prefix, numbers with `#`, separated by commas); several such lines add up.
The orchestrator writes it into design split issues that need an earlier step merged; `prefilter.py` drops blocked
issues from the start candidates. Bodies are untrusted text: only numbers are parsed, nothing is opened or run.
"""
import re

_LINE = re.compile(r"^Depends on: (#\d+(?:, *#\d+)*)[ \t\r]*$", re.MULTILINE)


def parse(body):
    """Issue numbers named in the `Depends on:` lines of BODY."""
    return {int(n) for line in _LINE.findall(body or "") for n in re.findall(r"\d+", line)}


def blocked(number, body, open_numbers):
    """True while an issue the body depends on is open; a reference to the issue itself is ignored."""
    return bool((parse(body) - {number}) & set(open_numbers))
