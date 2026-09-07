PYTHON_PROJECT := sdks/python
TYPESCRIPT_PROJECT := sdks/typescript
GO_PROJECT := sdks/go

.PHONY: version check-version fix fix-go lint lint-go lint-python lint-typescript test test-go test-python test-typescript test-version

version:
	python3 scripts/version.py
	uv lock --project $(PYTHON_PROJECT)
	$(MAKE) check-version

check-version:
	python3 scripts/version.py --check

fix:
	uv run --project $(PYTHON_PROJECT) --extra runner ruff format $(PYTHON_PROJECT) scripts
	uv run --project $(PYTHON_PROJECT) --extra runner ruff check --fix $(PYTHON_PROJECT) scripts
	$(MAKE) fix-go

fix-go:
	$(MAKE) -C $(GO_PROJECT) fix

lint: check-version
	$(MAKE) lint-python lint-typescript lint-go

lint-python:
	uv run --locked --project $(PYTHON_PROJECT) --extra runner ruff format --check $(PYTHON_PROJECT) scripts
	uv run --locked --project $(PYTHON_PROJECT) --extra runner ruff check $(PYTHON_PROJECT) scripts
	uv run --locked --project $(PYTHON_PROJECT) --extra runner mypy $(PYTHON_PROJECT)/src

lint-typescript:
	bun run --cwd $(TYPESCRIPT_PROJECT) typecheck

lint-go:
	$(MAKE) -C $(GO_PROJECT) lint

test: test-version test-python test-typescript test-go

test-version:
	python3 -m unittest discover -s scripts -p 'test_*.py'

test-python:
	uv run --project $(PYTHON_PROJECT) --extra runner pytest $(PYTHON_PROJECT)/tests

test-typescript:
	bun test --cwd $(TYPESCRIPT_PROJECT)

test-go:
	$(MAKE) -C $(GO_PROJECT) test
