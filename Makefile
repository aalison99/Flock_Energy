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

# --- Web client (frontend/) ---
.PHONY: web-install web web-build web-lint web-test web-types check-all

web-install:
	npm --prefix frontend ci

web:
	npm --prefix frontend run dev

web-build:
	npm --prefix frontend run build

web-lint:
	npm --prefix frontend run lint

web-test:
	npm --prefix frontend run test

web-types:
	npm --prefix frontend run gen:types

# make check stays backend-only; check-all adds the web client.
check-all: check web-lint web-test web-build
	npm --prefix frontend run check:types-drift
