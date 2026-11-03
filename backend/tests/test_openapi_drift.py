from pathlib import Path

from scripts.export_openapi import render


def test_committed_openapi_matches() -> None:
    committed = Path(__file__).resolve().parents[2] / "openapi.json"
    assert render() == committed.read_text()
