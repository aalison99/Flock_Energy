"""Devalue flat-array decoder."""

import json
import math
from pathlib import Path

import pytest

from app.portal.devalue import decode, decode_string

FIX = Path(__file__).parents[2] / "fixtures" / "portal"


def test_primitives() -> None:
    assert decode([5]) == 5
    assert decode(["x"]) == "x"
    assert decode([True]) is True
    assert decode([None]) is None


def test_nested() -> None:
    assert decode([{"a": 1, "b": 2}, "x", [3], 9]) == {"a": "x", "b": [9]}


def test_repeated_ref_identity() -> None:
    out = decode([{"a": 1, "b": 1}, [2], 5])
    assert isinstance(out, dict)
    assert out["a"] is out["b"]


@pytest.mark.parametrize("idx,expected", [(-1, None), (-2, None)])
def test_none_specials(idx: int, expected: object) -> None:
    assert decode([{"a": idx}]) == {"a": expected}


def test_float_specials() -> None:
    out = decode([{"n": -3, "p": -4, "m": -5, "z": -6}])
    assert isinstance(out, dict)
    assert math.isnan(out["n"])
    assert out["p"] == math.inf
    assert out["m"] == -math.inf
    assert out["z"] == 0.0
    assert math.copysign(1, out["z"]) == -1


def test_cycle() -> None:
    with pytest.raises(ValueError):
        decode([{"a": 0}])
    with pytest.raises(ValueError):
        decode([[1], [0]])


def test_tagged_array() -> None:
    with pytest.raises(ValueError, match="unsupported devalue type: Date"):
        decode([["Date", "2026-01-01"]])


def test_decode_string() -> None:
    assert decode_string(json.dumps([{"error": 1}, "bad"])) == {"error": "bad"}


def test_real_detail_page_node() -> None:
    body = json.loads((FIX / "meters" / "detail_legacy_J100000.json").read_text())
    out = decode(body["nodes"][2]["data"])
    assert isinstance(out, dict)
    assert out["meterId"] == "J100000"
    assert out["hierarchy"]["DT"] == "Malviya Nagar DT 1 (DT-001)"
    assert out["detail"]["data"][1] == {"parameterName": "Serial No", "parameterValue": "SE33962"}


@pytest.mark.parametrize("data", [[{"a": 5}], [{"a": "x"}], [[9]], [{"a": -9}], [[True]], []])
def test_bad_refs_are_value_errors(data: list[object]) -> None:
    with pytest.raises(ValueError):
        decode(data)


def test_too_deep() -> None:
    chain: list[object] = [[i + 1] for i in range(5000)] + [1]
    with pytest.raises(ValueError, match="nesting too deep"):
        decode(chain)
