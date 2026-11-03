"""Exports the app's OpenAPI schema to repo-root openapi.json (or checks it for drift)."""

import argparse
import json
import sys
from pathlib import Path

from app.core.config import Settings
from app.main import create_app

OPENAPI_PATH = Path(__file__).resolve().parents[2] / "openapi.json"


def render() -> str:
    """Return the canonical JSON text of the OpenAPI schema."""
    settings = Settings(
        portal_url="https://portal.example.test",
        portal_email="docs@example.test",
        portal_password="unused",
        _env_file=None,
    )
    return json.dumps(create_app(settings).openapi(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if openapi.json is stale")
    args = parser.parse_args(argv)
    text = render()
    if args.check:
        current = OPENAPI_PATH.read_text() if OPENAPI_PATH.exists() else ""
        if current != text:
            print("openapi.json is out of date; run: make openapi")
            return 1
        print("openapi.json is up to date")
        return 0
    OPENAPI_PATH.write_text(text)
    print(f"wrote {OPENAPI_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
