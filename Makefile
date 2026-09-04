PYTHON_PROJECT := sdks/python
TYPESCRIPT_PROJECT := sdks/typescript
GO_PROJECT := sdks/go

.PHONY: fix fix-go lint lint-go lint-python lint-typescript test test-go test-python test-typescript

fix:
	uv run --project $(PYTHON_PROJECT) --extra runner ruff format $(PYTHON_PROJECT)
	uv run --project $(PYTHON_PROJECT) --extra runner ruff check --fix $(PYTHON_PROJECT)
	$(MAKE) fix-go

fix-go:
	$(MAKE) -C $(GO_PROJECT) fix

lint: lint-python lint-typescript lint-go

lint-python:
	uv run --project $(PYTHON_PROJECT) --extra runner ruff format --check $(PYTHON_PROJECT)
	uv run --project $(PYTHON_PROJECT) --extra runner ruff check $(PYTHON_PROJECT)
	uv run --project $(PYTHON_PROJECT) --extra runner mypy $(PYTHON_PROJECT)/src

lint-typescript:
	bun run --cwd $(TYPESCRIPT_PROJECT) typecheck

lint-go:
	$(MAKE) -C $(GO_PROJECT) lint

test: test-python test-typescript test-go

test-python:
	uv run --project $(PYTHON_PROJECT) --extra runner pytest $(PYTHON_PROJECT)/tests

test-typescript:
	bun test --cwd $(TYPESCRIPT_PROJECT)

test-go:
	$(MAKE) -C $(GO_PROJECT) test
