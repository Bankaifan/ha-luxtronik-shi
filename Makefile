# Mirrors the validate workflow locally: `make check`. Needs the tools of tools/ci/install_tools.sh.
.PHONY: check
check:
	@if [ -n "$$(git ls-files '*.py')" ]; then ruff check .; else echo "no Python files"; fi
	@if [ -d tests ]; then pytest --timeout=60 -q; else echo "no tests/"; fi
	@if [ -n "$$(git ls-files '.github/workflows/*.yml')" ]; then \
		actionlint && zizmor --no-progress .github/workflows; else echo "no workflows"; fi
	python3 tools/check_version.py
	python3 tools/check/check_version.py
	python3 tools/check/check_pr_form.py
	python3 tools/check/check_no_bytecode.py
	python3 tools/check/check_var_defaults.py
	bash tools/check/check_drift.sh
