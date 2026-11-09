"""Create or update the issue "Weekly summary" without a model.

Sections: merged PRs of the last 7 days, PRs labelled needs-human, rule-keeper PRs,
ideas without `approved`. Needs the gh CLI (GH_TOKEN, GH_REPO).
"""
import datetime
import json
import subprocess
import sys

TITLE = "Weekly summary"


def section(heading, rows):
    lines = [f"## {heading}"]
    lines += [f"- #{r['number']} {r['title']}" for r in rows] or ["- none"]
    return "\n".join(lines)


def build_body(merged, needs_human, rule_keeper, ideas, today):
    parts = [f"Updated {today}.", section("Merged in the last 7 days", merged),
             section("PRs labelled needs-human", needs_human),
             section("Rule-keeper PRs", rule_keeper),
             section("Ideas waiting for approval", ideas)]
    return "\n\n".join(parts) + "\n"


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def main() -> int:
    today = datetime.date.today()
    since = (today - datetime.timedelta(days=7)).isoformat()
    merged = json.loads(gh("pr", "list", "--state", "merged", "--limit", "100",
                           "--search", f"merged:>={since}", "--json", "number,title"))
    human = json.loads(gh("pr", "list", "--state", "open", "--label", "needs-human", "--json", "number,title"))
    prs = json.loads(gh("pr", "list", "--state", "open", "--limit", "100", "--json", "number,title,headRefName"))
    keeper = [p for p in prs if p["headRefName"].startswith("agent/rule-keeper-")]
    ideas = [i for i in json.loads(gh("issue", "list", "--state", "open", "--label", "idea", "--limit", "100",
                                      "--json", "number,title,labels"))
             if "approved" not in {lab["name"] for lab in i["labels"]}]
    body = build_body(merged, human, keeper, ideas, today.isoformat())
    found = json.loads(gh("issue", "list", "--state", "open", "--search", f'"{TITLE}" in:title',
                          "--json", "number,title"))
    found = [i for i in found if i["title"] == TITLE]
    if found:
        gh("issue", "edit", str(found[0]["number"]), "--body", body)
        print(f"updated #{found[0]['number']}")
    else:
        print(gh("issue", "create", "--title", TITLE, "--body", body).strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
