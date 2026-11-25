# Project hook (design 0016): project.mk (not managed) adds `project-check::` recipes; a missing file is not an error.
.DEFAULT_GOAL := check
-include project.mk

# Test scoping (design 0009): on pull requests (PR_BASE_REF set) only the tests covering the changed files run.
# Output of tools/scope_tests.py: ALL (everything), a file list, or empty (nothing in scope). Unset PR_BASE_REF = ALL.
SCOPE_OUT = $(shell if [ -n "$$PR_BASE_REF" ]; then python3 tools/scope_tests.py "origin/$$PR_BASE_REF"; else echo ALL; fi)
SCOPE_FILES = $(filter-out ALL,$(SCOPE_OUT))
# Slow tests are deselected only when NIGHTLY_HEAVY_TESTS is exactly "true" (they then run in the nightly workflow).
SLOW_FILTER = $(if $(filter true,$(NIGHTLY_HEAVY_TESTS)),-m "not slow")

# Scope ALL (full run): measure line coverage of tools/ and hold it to the floor in docs/coverage.json (check_coverage.py).
# Without docs/coverage.json (downstream projects) the plain pytest run is used.
COVERAGE_RUN = if [ -f docs/coverage.json ] && python3 -c "import coverage" 2>/dev/null; then coverage run --source=tools "$$(command -v pytest)" --timeout=60 -q $(SLOW_FILTER) && python3 tools/check/check_coverage.py; else pytest --timeout=60 -q $(SLOW_FILTER); fi

# Mirrors the validate workflow locally: `make check`. Needs the tools of tools/ci/install_tools.sh.
# `check` is exactly the four targets below, in this order; validate.yml runs each as its own job.
.PHONY: check
check:
	@$(MAKE) --no-print-directory check-lint
	@$(MAKE) --no-print-directory check-tests
	@$(MAKE) --no-print-directory check-workflows
	@$(MAKE) --no-print-directory check-repo

.PHONY: check-lint
check-lint:
	@if [ -n "$$(git ls-files '*.py')" ]; then ruff check .; else echo "no Python files"; fi
	@$(MAKE) --no-print-directory type-check

.PHONY: check-tests
check-tests:
	@$(MAKE) --no-print-directory unit-tests

.PHONY: check-workflows
check-workflows:
	@if [ -n "$$(git ls-files '.github/workflows/*.yml')" ]; then \
		actionlint && zizmor --no-progress .github/workflows; else echo "no workflows"; fi

.PHONY: check-repo
check-repo:
	python3 tools/check_version.py
	python3 tools/check/check_version.py
	python3 tools/check/check_pr_form.py
	python3 tools/managed_guard.py check
	python3 tools/check/check_no_bytecode.py
	python3 tools/check/check_var_defaults.py
	python3 tools/check/check_budget.py
	python3 tools/design_split.py check
	bash tools/check/check_drift.sh
	@$(MAKE) --no-print-directory test-evidence
	@$(MAKE) --no-print-directory project-check

# The checks that read the PR title or body. validate.yml runs only these when a PR's text was edited and its head
# commit already has a green full run (the code did not change).
.PHONY: check-text
check-text:
	python3 tools/check/check_pr_form.py
	python3 tools/managed_guard.py check
	@$(MAKE) --no-print-directory test-evidence

# Empty template default: project.mk adds recipes with `project-check::` (double-colon rules run in order).
.PHONY: project-check
project-check::
	@:

.PHONY: type-check
type-check:
	@if [ -n "$$(git ls-files 'tools/*.py')" ]; then mypy --config-file mypy.ini tools; else echo "no Python files in tools/"; fi

.PHONY: unit-tests
unit-tests:
	@if [ -d tests ]; then $(if $(strip $(SCOPE_OUT)),$(if $(SCOPE_FILES),pytest --timeout=60 -q $(SLOW_FILTER) $(SCOPE_FILES) && python3 tools/check/check_coverage.py --scoped,$(COVERAGE_RUN)),echo "no tests in scope"); else echo "no tests/"; fi

# Pull requests only: PR_BASE_REF is the base branch name (set by validate.yml); skipped when unset (local runs, pushes).
.PHONY: test-evidence
test-evidence:
	@if [ -n "$$PR_BASE_REF" ]; then python3 tools/check/check_test_evidence.py "origin/$$PR_BASE_REF"; else echo "check_test_evidence: skipped (no PR_BASE_REF)"; fi
