"""Which design studies are the template's own (issue #674). Only reads files: no gh, no git, no model.

`TEMPLATE_DESIGNS` lists the `docs/design/NNNN-slug.md` studies the template ships. A downstream project (one with
.agents/template.json) splits none of them (tools/design_split.py) and takes no parent from their `Issue: #N` header
(tools/design_parents.py). The template repo has no .agents/template.json and keeps its own designs as before.
The list lives in this file, not in .agents/managed.json, because tools/ is a managed prefix: template sync delivers it
to every downstream project, including ones that imported the template before this change. A test
(tests/agent/test_design_origin.py) requires every design of the template to be listed.
"""
import pathlib

TEMPLATE_DESIGNS = frozenset({
    "docs/design/0001-template-sync.md", "docs/design/0002-unblocker-role.md", "docs/design/0003-merge-train.md",
    "docs/design/0004-untrusted-text-boundary.md", "docs/design/0005-risk-tightening.md", "docs/design/0006-answer-receiver.md",
    "docs/design/0007-orchestrator-events.md", "docs/design/0008-failure-watch.md", "docs/design/0009-test-scoping.md",
    "docs/design/0010-large-sync-security-review.md", "docs/design/0011-automatic-template-sync.md", "docs/design/0012-actions-watcher.md",
    "docs/design/0013-parallel-pr-version-conflicts.md", "docs/design/0014-template-sync-by-script.md", "docs/design/0015-model-free-dispatcher.md",
    "docs/design/0016-extension-points.md", "docs/design/0017-safety-boundary.md",
})


def template_internal(root):
    """Design paths the template ships as its own studies; empty set outside a downstream project."""
    if not (pathlib.Path(root) / ".agents" / "template.json").is_file():
        return set()
    return set(TEMPLATE_DESIGNS)
