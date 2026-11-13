"""Required checks of `main` (design 0016, section 4.3): the template ruleset plus the project's own checks.

The template list is `.github/rulesets/main.json`. A project adds required checks in `.agents/checks.json`
(`{"required": ["name", ...]}`, not managed, owner-guarded by CODEOWNERS). A name is lowercase letters, digits and
hyphens, at most 63 characters; a name twice in the list, or a name the template already requires, is refused.
Nothing applies a ruleset by itself: Daniel imports the `build` output by hand (README, setup step 4).

CLI:
  ruleset.py build   print the template ruleset with the project checks added (JSON on stdout);
                     exit 1 with the reason on stderr when `.agents/checks.json` or the template is malformed
"""
import json
import os
import re
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
RULESET_PATH = os.path.join(TOOLS, os.pardir, ".github", "rulesets", "main.json")
CHECKS_PATH = os.path.join(TOOLS, os.pardir, ".agents", "checks.json")
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")


def template_contexts(path=RULESET_PATH):
    """Context names of the template's required_status_checks rules (a set, empty if none). Raises on a bad file."""
    with open(path, encoding="utf-8") as f:
        ruleset = json.load(f)
    return {c["context"] for rule in ruleset["rules"] if rule["type"] == "required_status_checks"
            for c in rule["parameters"]["required_status_checks"]}


def project_checks(path=CHECKS_PATH):
    """Names from `.agents/checks.json`; [] if the file does not exist. ValueError if the file is malformed."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return []
    if not isinstance(data, dict) or set(data) != {"required"} or not isinstance(data["required"], list):
        raise ValueError(f'{path} must be {{"required": [names]}}')
    names = data["required"]
    bad = [n for n in names if not isinstance(n, str) or not NAME.fullmatch(n)]
    if bad:
        raise ValueError(f"malformed check names (lowercase letters, digits, hyphens; max 63): {bad}")
    twice = sorted({n for n in names if names.count(n) > 1})
    if twice:
        raise ValueError(f"duplicate check names: {twice}")
    return names


def contexts(ruleset_path=RULESET_PATH, checks_path=CHECKS_PATH):
    """Every required context: the template's plus the project's. A project name the template already has is refused."""
    template = template_contexts(ruleset_path)
    project = project_checks(checks_path)
    clash = sorted(set(project) & template)
    if clash:
        raise ValueError(f"checks.json repeats template checks: {clash}")
    return template | set(project)


def build(ruleset_path=RULESET_PATH, checks_path=CHECKS_PATH):
    """The template ruleset with the project checks appended to its required_status_checks, as JSON text."""
    contexts(ruleset_path, checks_path)  # validates both files before anything is written
    with open(ruleset_path, encoding="utf-8") as f:
        ruleset = json.load(f)
    rules = [r for r in ruleset["rules"] if r["type"] == "required_status_checks"]
    if len(rules) != 1:
        raise ValueError(f"the template ruleset needs exactly one required_status_checks rule, found {len(rules)}")
    rules[0]["parameters"]["required_status_checks"] += [{"context": n} for n in project_checks(checks_path)]
    return json.dumps(ruleset, indent=2) + "\n"


def main(argv):
    if argv[1:] != ["build"]:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        sys.stdout.write(build())
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"ruleset build refused: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
