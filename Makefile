# Test scoping (design 0009): on pull requests (PR_BASE_REF set) only the tests covering the changed files run.
# Output of tools/scope_tests.py: ALL (everything), a file list, or empty (nothing in scope). Unset PR_BASE_REF = ALL.
SCOPE_OUT = $(shell if [ -n "$$PR_BASE_REF" ]; then python3 tools/scope_tests.py "origin/$$PR_BASE_REF"; else echo ALL; fi)
SCOPE_FILES = $(filter-out ALL,$(SCOPE_OUT))
# Slow tests are deselected only when NIGHTLY_HEAVY_TESTS is exactly "true" (they then run in the nightly workflow).
SLOW_FILTER = $(if $(filter true,$(NIGHTLY_HEAVY_TESTS)),-m "not slow")

# Mirrors the validate workflow locally: `make check`. Needs the tools of tools/ci/install_tools.sh.
.PHONY: check
check:
	@if [ -n "$$(git ls-files '*.py')" ]; then ruff check .; else echo "no Python files"; fi
	@$(MAKE) --no-print-directory unit-tests
	@if [ -n "$$(git ls-files '.github/workflows/*.yml')" ]; then \
		actionlint && zizmor --no-progress .github/workflows; else echo "no workflows"; fi
	python3 tools/check_version.py
	python3 tools/check/check_version.py
	python3 tools/check/check_pr_form.py
	python3 tools/managed_guard.py check
	python3 tools/check/check_no_bytecode.py
	python3 tools/check/check_var_defaults.py
	bash tools/check/check_drift.sh
	@$(MAKE) --no-print-directory test-evidence

.PHONY: unit-tests
unit-tests:
	@if [ -d tests ]; then $(if $(strip $(SCOPE_OUT)),pytest --timeout=60 -q $(SLOW_FILTER) $(SCOPE_FILES),echo "no tests in scope"); else echo "no tests/"; fi

# Pull requests only: PR_BASE_REF is the base branch name (set by validate.yml); skipped when unset (local runs, pushes).
.PHONY: test-evidence
test-evidence:
	@if [ -n "$$PR_BASE_REF" ]; then python3 tools/check/check_test_evidence.py "origin/$$PR_BASE_REF"; else echo "check_test_evidence: skipped (no PR_BASE_REF)"; fi
