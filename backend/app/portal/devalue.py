"""Decoder for SvelteKit's devalue flat-array format (the subset the portal emits)."""

import json
import math

_SPECIALS: dict[int, object] = {
    -1: None,
    -2: None,
    -3: math.nan,
    -4: math.inf,
    -5: -math.inf,
    -6: -0.0,
}


MAX_DEPTH = 200


def decode(data: list[object]) -> object:
    """Decode a devalue array: index 0 is the root, containers hold indices into `data`.

    Raises ValueError for any malformed input (bad index, cycle, too deep, unsupported tag).
    """
    if not isinstance(data, list):
        raise ValueError("devalue data must be a list")
    done: dict[int, object] = {}
    active: set[int] = set()

    def resolve(idx: int) -> object:
        if idx < 0:
            if idx in _SPECIALS:
                return _SPECIALS[idx]
            raise ValueError(f"unknown devalue special index: {idx}")
        if idx >= len(data):
            raise ValueError(f"devalue index out of range: {idx}")
        if idx in done:
            return done[idx]
        if idx in active:
            raise ValueError(f"cycle in devalue data at index {idx}")
        if len(active) >= MAX_DEPTH:
            raise ValueError("devalue nesting too deep")
        active.add(idx)
        value = data[idx]
        out: object
        if isinstance(value, list):
            if value and isinstance(value[0], str):
                raise ValueError(f"unsupported devalue type: {value[0]}")
            out = [resolve(_index(i)) for i in value]
        elif isinstance(value, dict):
            out = {k: resolve(_index(i)) for k, i in value.items()}
        else:
            out = value
        active.discard(idx)
        done[idx] = out
        return out

    return resolve(0)


def _index(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"devalue reference must be an integer index, got {value!r}")
    return value


def decode_string(s: str) -> object:
    """Decode a devalue array carried as a JSON string."""
    return decode(json.loads(s))
