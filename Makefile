# Mirrors the Validate workflow locally: `make check`. Needs the tools of tools/ci/install_tools.sh.
.PHONY: check
check:
	ruff check .
	pytest --timeout=60 -q
	python3 tools/check_version.py
	python3 tools/check/check_no_bytecode.py
	bash tools/check/check_drift.sh
	actionlint
	zizmor --no-progress .github/workflows
