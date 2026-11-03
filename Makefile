.PHONY: install lint format typecheck layering test test-live openapi openapi-check check run

install:
	cd backend && uv sync --locked

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .

format:
	cd backend && uv run ruff format . && uv run ruff check --fix .

typecheck:
	cd backend && uv run mypy app scripts

layering:
	cd backend && uv run python scripts/check_layering.py

test:
	cd backend && uv run pytest

test-live:
	cd backend && uv run pytest -m live

openapi:
	cd backend && uv run python -m scripts.export_openapi

openapi-check:
	cd backend && uv run python -m scripts.export_openapi --check

check: lint typecheck layering test openapi-check

# NB: with --reload, uvicorn's reloader keeps running after a startup SystemExit (bad config).
run:
	cd backend && uv run uvicorn app.main:create_app_from_env --factory --reload --port 8000
