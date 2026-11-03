"""An in-process emulator of the Urja portal for httpx.MockTransport, built from the fixtures.

It models sessions, the three no-session signals, search paging, signed export and sign-out,
plus test controls for expiry, injected failures and secret rotation.
"""

import json
from datetime import date, datetime
from pathlib import Path
from urllib.parse import unquote

import httpx

from app.portal.signer import HmacSha256Signer

FIXTURES = Path(__file__).parents[1] / "fixtures" / "portal"
COOKIE_NAME = "__Secure-better-auth.session_token"
PAGE_SIZE = 20
DETAIL_FIXTURES = {
    "J100000": "detail_legacy_J100000.json",
    "J100086": "detail_v2_J100086.json",
    "J100402": "detail_legacy_J100402_old_dt_name.json",
}


class PortalEmulator:
    """Behaves like the portal; use `httpx.MockTransport(emulator.handle)`."""

    def __init__(
        self,
        fixtures_dir: Path = FIXTURES,
        *,
        email: str = "tester@example.test",
        origin: str = "https://portal.example.test",
    ) -> None:
        self._dir = fixtures_dir
        self._email = email
        self._origin = origin
        self.password = "emulator-password"
        self.secret = "test-signing-secret"
        records = json.loads((fixtures_dir / "export" / "export_page1.json").read_bytes())["data"]
        self._records: list[dict[str, object]] = records
        self._by_id = {str(r["meterId"]): r for r in records}
        self._tokens: set[str] = set()
        self._token_seq = 0
        self._failures: list[tuple[int | None, Exception | None]] = []
        self.logins = 0
        self.requests: list[tuple[str, str]] = []
        self.queries: list[str] = []
        self.request_log: list[httpx.Request] = []

    # ---- test controls -------------------------------------------------------------------
    def expire_sessions(self) -> None:
        """Invalidate every token, so the next authenticated call sees an expired session."""
        self._tokens.clear()

    def fail_next(
        self, n: int = 1, *, status: int | None = 503, exception: Exception | None = None
    ) -> None:
        """Make the next `n` requests fail with `exception` or an HTTP `status`."""
        self._failures.extend([(None if exception else status, exception)] * n)

    def rotate_secret(self, new: str) -> None:
        self.secret = new

    # ---- helpers -------------------------------------------------------------------------
    def _fx(self, *parts: str) -> bytes:
        return (self._dir.joinpath(*parts)).read_bytes()

    @staticmethod
    def _json(body: bytes | str, status: int = 200) -> httpx.Response:
        content = body.encode() if isinstance(body, str) else body
        return httpx.Response(status, content=content, headers={"content-type": "application/json"})

    @staticmethod
    def _token(request: httpx.Request) -> str:
        for part in request.headers.get("cookie", "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == COOKIE_NAME:
                return value
        return ""

    def _valid_token(self, request: httpx.Request) -> bool:
        return self._token(request) in self._tokens

    # ---- entry point ---------------------------------------------------------------------
    def handle(self, request: httpx.Request) -> httpx.Response:
        raw_path = request.url.raw_path.decode().split("?", 1)[0]
        self.requests.append((request.method, raw_path))
        self.queries.append(request.url.query.decode())
        self.request_log.append(request)
        if self._failures:
            status, exc = self._failures.pop(0)
            if exc is not None:
                raise exc
            return httpx.Response(status or 503, content=b"unavailable")
        if request.method == "POST" and raw_path == "/login":
            return self._login(request)
        if request.method == "POST" and raw_path == "/api/auth/sign-out":
            self._tokens.discard(self._token(request))
            return self._json("{}")
        if not self._valid_token(request):
            return self._no_session(raw_path)
        return self._route(request, raw_path)

    def _no_session(self, path: str) -> httpx.Response:
        if path.startswith("/portal/"):
            return self._json(self._fx("auth", "portal_unauthorized.json"), 401)
        if path.endswith("/__data.json"):
            return self._json(self._fx("auth", "sveltekit_redirect_to_login.json"))
        return httpx.Response(302, headers={"location": "/login"})

    def _login(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("origin") != self._origin:
            return self._json(self._fx("auth", "login_cross_site_forbidden.json"), 403)
        form = dict(httpx.QueryParams(request.content.decode()))
        if form.get("email") != self._email or form.get("password") != self.password:
            return self._json(self._fx("auth", "login_bad_password.json"))
        self.logins += 1
        self._token_seq += 1
        token = f"token-{self._token_seq}"
        self._tokens.add(token)
        cookie = f"{COOKIE_NAME}={token}; Path=/; HttpOnly; Secure; SameSite=Lax"
        response = self._json(self._fx("auth", "login_ok.json"))
        response.headers["set-cookie"] = cookie
        return response

    def _route(self, request: httpx.Request, path: str) -> httpx.Response:
        params = request.url.params
        if path == "/portal/meters/search":
            return self._search(params.get("q", ""), params.get("page", "1"))
        if path == "/portal/dts":
            return self._dts(params.get("page", "1"))
        if path == "/meters":  # an HTML page: used to exercise the 302 expiry signal
            return httpx.Response(200, content=b"<html></html>")
        if path == "/portal/keys":
            return self._json(json.dumps({"data": {"signingSecret": self.secret}}))
        if path == "/portal/export":
            return self._export(request)
        if path.startswith("/meters/") and path.endswith("/__data.json"):
            return self._detail(unquote(path[len("/meters/") : -len("/__data.json")]))
        if path.startswith("/portal/meters/"):
            raw_id, _, tail = path[len("/portal/meters/") :].partition("/")
            meter_id = unquote(raw_id)
            if tail == "geo":
                return self._geo(meter_id)
            if tail == "energy":
                return self._energy(meter_id, params.get("from"), params.get("to"))
        return httpx.Response(404, content=b"not found")

    # ---- routes --------------------------------------------------------------------------
    def _search(self, q: str, page_raw: str) -> httpx.Response:
        page = int(page_raw) if page_raw.isdigit() and int(page_raw) >= 1 else 1
        needle = q.lower()
        matches = [
            r
            for r in self._records
            if needle in str(r["meterId"]).lower() or needle in str(r["serialNo"]).lower()
        ]
        keys = ("meterId", "serialNo", "make", "phaseType", "installStatus", "dtCode")
        window = matches[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
        body = {
            "data": [{k: r[k] for k in keys} for r in window],
            "total": len(matches),
            "page": page,
            "pageSize": PAGE_SIZE,
        }
        return self._json(json.dumps(body))

    def _dts(self, page_raw: str) -> httpx.Response:
        page = int(page_raw) if page_raw.isdigit() and int(page_raw) >= 1 else 1
        name = f"page{page}.json" if page in (1, 2) else "page3_past_end.json"
        return self._json(self._fx("dts", name))

    def _export(self, request: httpx.Request) -> httpx.Response:
        sent = request.headers.get("x-signature")
        timestamp = request.headers.get("x-timestamp", "")
        if sent and timestamp.isdigit():
            query = request.url.query.decode()
            expected = HmacSha256Signer().sign(
                "GET", request.url.path, query, self.secret, int(timestamp)
            )["x-signature"]
            if expected == sent:
                return self._json(self._fx("export", "export_page1.json"))
        return self._json(self._fx("export", "signature_invalid.json"), 401)

    def _detail(self, meter_id: str) -> httpx.Response:
        if meter_id in DETAIL_FIXTURES:
            return self._json(self._fx("meters", DETAIL_FIXTURES[meter_id]))
        if meter_id in self._by_id:
            # Deliberately loud: only fixture IDs have detail payloads.
            return httpx.Response(500, content=b"emulator has no detail fixture for this meter")
        return self._json(self._fx("meters", "detail_not_found.json"))

    def _not_found(self) -> httpx.Response:
        return self._json(self._fx("meters", "portal_not_found.json"), 404)

    def _geo(self, meter_id: str) -> httpx.Response:
        record = self._by_id.get(meter_id)
        if record is None:
            return self._not_found()
        geo = record["geo"]
        assert isinstance(geo, dict)
        data = {"latitude": str(geo["lat"]), "longitude": str(geo["lng"])}
        return self._json(json.dumps({"data": data}))

    def _energy(self, meter_id: str, start: str | None, end: str | None) -> httpx.Response:
        if meter_id not in self._by_id:
            return self._not_found()
        files = sorted((self._dir / "energy").glob(f"*_{meter_id}.json"))
        if not files:
            return self._json('{"data":[]}')
        rows: list[dict[str, str]] = json.loads(files[0].read_bytes())["data"]
        lo = date.fromisoformat(start) if start else None
        hi = date.fromisoformat(end) if end else None

        def keep(row: dict[str, str]) -> bool:
            day = datetime.strptime(row["timestamp"], "%d/%m/%Y %H:%M").date()
            return (lo is None or day >= lo) and (hi is None or day <= hi)

        return self._json(json.dumps({"data": [r for r in rows if keep(r)]}))
