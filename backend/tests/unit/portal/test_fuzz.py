"""Deterministic fuzz: no parser may leak anything but the documented exceptions.

The explicit reviewer repros are the regression guard; the seeded fuzz loop is a smoke test.
"""

import contextlib
import json
import random

import pytest

from app.domain.exceptions import NotFoundError, UpstreamAuthError, UpstreamProtocolError
from app.portal.errors import SessionExpired, SignatureRejected
from app.portal.parsers.registry import PayloadKind, default_registry

ALLOWED = (
    UpstreamProtocolError,
    NotFoundError,
    UpstreamAuthError,
    SessionExpired,
    SignatureRejected,
)
registry = default_registry()
KEYS = [
    "data",
    "total",
    "page",
    "pageSize",
    "type",
    "nodes",
    "error",
    "message",
    "latitude",
    "longitude",
    "signingSecret",
    "kwh",
    "kvah",
    "voltR",
    "timestamp",
    "capacityKva",
    "meterId",
    "hierarchy",
    "detail",
    "classData",
    "status",
    "location",
]


def junk(rng: random.Random, depth: int = 0) -> object:
    pick = rng.randrange(10 if depth < 4 else 6)
    if pick == 0:
        return None
    if pick == 1:
        return rng.choice([True, False])
    if pick == 2:
        return rng.choice([0, -1, 7, 10**400, -(10**400), 2**63])
    if pick == 3:
        return rng.choice([1.5, float("1e308"), -0.0])
    if pick == 4:
        return rng.choice(["", " ", "abc", "01/01/2026 00:00", "1e999", "nan", "(", "x (y)", "1_0"])
    if pick == 5:
        return rng.choice(["unauthorized", "not_found", "signature_invalid", "redirect", "failure"])
    if pick in (6, 7):
        return [junk(rng, depth + 1) for _ in range(rng.randrange(4))]
    return {rng.choice(KEYS): junk(rng, depth + 1) for _ in range(rng.randrange(5))}


def payloads() -> list[bytes]:
    rng = random.Random(1234)
    out: list[bytes] = [b"", b"null", b"[", b'"x"', bytes(rng.randrange(256) for _ in range(64))]
    out += [json.dumps(junk(rng)).encode() for _ in range(300)]
    out += [
        json.dumps({rng.choice(KEYS): junk(rng) for _ in range(4)}).encode() for _ in range(200)
    ]
    out.append(b'{"data":[' + b",".join([b"{}"] * 20000) + b"]}")
    out.append(b'{"data":[],"total":10,"page":1,"pageSize":20}')
    return out


# The reviewer's exact repros.
HUGE = "1" + "0" * 400
REPROS = [
    ("ENERGY", f'{{"data":[{{"timestamp":"01/01/2026 00:00","kwh":{HUGE},"kvah":1,"voltR":1}}]}}'),
    ("ENERGY", f'{{"data":[{{"timestamp":"01/01/2026 00:00","kwh":1,"kvah":1,"voltR":{HUGE}}}]}}'),
    (
        "DT_PAGE",
        f'{{"data":[{{"code":"a","name":"b","capacityKva":{HUGE}}}],"total":1,"page":1,"pageSize":20}}',
    ),
    ("GEO", "[" * 100000),
    ("METER_DETAIL", "[" * 100000),
    ("LOGIN_ACTION", "[" * 100000),
    ("GEO", '{"data":' + "[" * 100000),
    (
        "LOGIN_ACTION",
        json.dumps({"type": "failure", "data": json.dumps([[i + 1] for i in range(5000)] + [1])}),
    ),
    (
        "METER_DETAIL",
        json.dumps(
            {
                "type": "data",
                "nodes": [
                    None,
                    None,
                    {"type": "data", "data": [[i + 1] for i in range(5000)] + [1]},
                ],
            }
        ),
    ),
]


@pytest.mark.parametrize("kind", list(PayloadKind))
def test_garbage_only_raises_allowed(kind: PayloadKind) -> None:
    for body in payloads():
        with contextlib.suppress(*ALLOWED):
            registry.parse(kind, body)


@pytest.mark.parametrize(("name", "body"), REPROS)
def test_reviewer_repros(name: str, body: str) -> None:
    with pytest.raises(UpstreamProtocolError):
        registry.parse(PayloadKind[name], body.encode())
