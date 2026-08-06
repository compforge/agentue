PYTHON_PROJECT := sdks/python
TYPESCRIPT_PROJECT := sdks/typescript

.PHONY: fix lint lint-python lint-typescript test test-python test-typescript

fix:
	uv run --project $(PYTHON_PROJECT) --extra runner ruff format $(PYTHON_PROJECT)
	uv run --project $(PYTHON_PROJECT) --extra runner ruff check --fix $(PYTHON_PROJECT)

lint: lint-python lint-typescript

lint-python:
	uv run --project $(PYTHON_PROJECT) --extra runner ruff format --check $(PYTHON_PROJECT)
	uv run --project $(PYTHON_PROJECT) --extra runner ruff check $(PYTHON_PROJECT)
	uv run --project $(PYTHON_PROJECT) --extra runner mypy $(PYTHON_PROJECT)/src

lint-typescript:
	bun run --cwd $(TYPESCRIPT_PROJECT) typecheck

test: test-python test-typescript

test-python:
	uv run --project $(PYTHON_PROJECT) --extra runner pytest $(PYTHON_PROJECT)/tests

test-typescript:
	bun test --cwd $(TYPESCRIPT_PROJECT)
