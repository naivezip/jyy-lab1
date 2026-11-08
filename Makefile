UV ?= uv

.PHONY: ci sync lint test

ci: sync lint test

sync:
	$(UV) sync --locked

lint: sync
	$(UV) run ruff check .
	$(UV) run ruff format --check .

test: sync
	@if [ -d tests ] && find tests -type f -name 'test_*.py' | grep -q .; then \
		$(UV) run pytest; \
	else \
		echo "No test files yet; pytest skipped (CI bootstrap)."; \
	fi
