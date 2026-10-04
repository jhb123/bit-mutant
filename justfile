test:
    uv run pytest -s -v

lint:
    uv run ruff check --fix
    uv run ruff format
examples:
    uv run pytest -s -v examples
