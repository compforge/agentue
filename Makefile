PYTHON_PROJECT := sdks/python

.PHONY: fix lint test

fix:
	uv run --project $(PYTHON_PROJECT) --extra runner ruff format $(PYTHON_PROJECT)
	uv run --project $(PYTHON_PROJECT) --extra runner ruff check --fix $(PYTHON_PROJECT)

lint:
	uv run --project $(PYTHON_PROJECT) --extra runner ruff format --check $(PYTHON_PROJECT)
	uv run --project $(PYTHON_PROJECT) --extra runner ruff check $(PYTHON_PROJECT)
	uv run --project $(PYTHON_PROJECT) --extra runner mypy $(PYTHON_PROJECT)/src

test:
	uv run --project $(PYTHON_PROJECT) --extra runner pytest $(PYTHON_PROJECT)/tests
