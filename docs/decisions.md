# Design decisions

Short ADR-style entries, one per decision, in the order they were made. Each says what was decided, why, and what it costs. The README's "Design decisions & trade-offs" section summarises these.

---

### ADR-001: Python + FastAPI for the API
- **Decision:** Python 3.13 with FastAPI and Pydantic.
- **Why:** FastAPI generates the OpenAPI 3 document and Swagger UI from the code, so `openapi.json` is always in sync with what runs. Pydantic validates every request at the edge.
- **Cost:** none of note for a service of this size.

### ADR-002: React + Vite for the web client, organised by feature
- **Decision:** React + Vite + TypeScript, Leaflet (OpenStreetMap tiles) for maps, Recharts for charts. Each feature folder exposes one public `index.ts`, and only its `api.ts` makes HTTP calls.
- **Why:** everything is free and runs locally. The feature boundaries mirror the backend layering, and the API types are generated from `openapi.json`, so an API change breaks the frontend build instead of failing at runtime.
- **Cost:** a second toolchain (Node) to install.

### ADR-003: Use the portal's signed bulk export
- **Decision:** sync the full meter dataset through `GET /portal/export`, signing requests the way the portal's own "Export all meters" button does (HMAC-SHA256, see PROTOCOL.md §3.6). Per-meter crawling is the fallback.
- **Why:** one call instead of ~1,200, and it is a feature available to any logged-in user.
- **Cost:** it depends on an undocumented signing scheme. If the portal changes it, the client falls back to crawling.

### ADR-004: Phase order: robustness before the core API
- **Decision:** build the retry/circuit-breaker and caching wrappers before the core endpoints. Merge "bulk dataset" into the local-index phase. Add a data-quality report and an analytics phase.
- **Why:** endpoints are robust from their first request; the index needs the export as its source; the web client's health views need an API behind them.
- **Cost:** the first visible endpoint arrives a little later.

### ADR-005: Hierarchy nodes are identified by their full code path
- **Decision:** a node's ID is its chain of codes (e.g. `Z-01/C-01/D-07/SD-07/SS-07/F-007`). DTs keep their own code, which is globally unique.
- **Why:** in the portal, codes below zone level are only unique under their parent (`D-01` sits under three circles). Read globally they form a tangled graph; as paths they form a clean tree with one name per node.
- **Cost:** node IDs are longer, so the API also returns `code` and `name` separately for display.

### ADR-006: The DT list's name is canonical
- **Decision:** when sources disagree on a transformer's name, the DT list wins. Other names are kept as aliases and reported under `/data-quality`.
- **Why:** the DT list is the portal's dedicated transformer source. DT-007's second name comes only from three late-added meters.
- **Cost:** if the DT list itself is stale, we present the old name, though the alias stays visible.

### ADR-007: Repair blank hierarchy fields, and report every repair
- **Decision:** when a hierarchy level has a code but no name (or a name but no code), fill it in from the number rule ("Circle 6" ↔ `C-06`) or from the node's canonical name, and list each repair with before/after values.
- **Why:** 22 meters have exactly one such blank. The rule held for every complete pair in the dataset, so a repair is safe, and reporting it keeps it honest.
- **Cost:** a wrong repair is possible if the rule ever breaks. The report makes that visible.

### ADR-008: Detect each meter's reading interval from its data
- **Decision:** infer whether a series is half-hourly or daily from its timestamps, instead of assuming one interval.
- **Why:** both exist, and no meter attribute predicts which one a meter uses.
- **Cost:** a series with very few points can't be classified; it's reported as `unknown`.

### ADR-009: Portal timestamps are treated as IST
- **Decision:** parse the portal's timezone-less `dd/mm/yyyy HH:MM` as Asia/Kolkata, and return ISO 8601 with `+05:30`.
- **Why:** the utility is in Jaipur, and daily readings align to local midnight.
- **Cost:** if the portal actually used UTC, every timestamp would be off by 5.5 hours. This is listed as an assumption in the README.

### ADR-010: uv, with Python pinned to 3.13
- **Decision:** manage the backend with uv and a lockfile, on Python 3.13.
- **Why:** reproducible installs with one command. 3.13 has mature wheels for every dependency.
- **Cost:** reviewers need uv installed (one command, documented in the README).

### ADR-011: Test the HTTP client against a fixture-built portal emulator
- **Decision:** the real `HttpPortalClient` is tested through `httpx.MockTransport` with an emulator that answers like the portal (login, cookies, expiry signals, search rules, signed export), built from the captured fixtures. The same contract suite runs against the fake, the HTTP client, and (opt-in) the live portal.
- **Why:** one suite proves all three behave identically; default test runs never touch the network.
- **Cost:** the emulator can drift from the real portal; the opt-in live suite is the check on that.

### ADR-012: Caching TTLs and stale-on-error
- **Decision:** cache nameplate-type portal data (meter list/detail, geo, transformers) for 24 h and readings for 15 min; never cache the bulk export (the local index is its cache). When the portal is unavailable and an expired entry exists, serve it marked `stale: true`.
- **Why:** nameplate data rarely changes and the finest reading interval is 30 min; serving slightly old data with an explicit flag beats failing while the portal is down.
- **Cost:** a value can be up to one TTL out of date; no single-flight de-duplication, so simultaneous cache misses for one key each hit the portal (harmless at this data size).

### ADR-013: Retry only "unavailable" errors; circuit breaker with per-call permits
- **Decision:** retry timeouts/5xx/429 up to 3 attempts with jittered exponential backoff (honouring Retry-After up to a cap); never retry not-found, auth or protocol errors. After 5 consecutive failures (auth failures included) the circuit opens for 30 s, then admits one half-open trial. Every call gets a permit at admission; once the circuit has opened, only the current trial's permit can close or reopen it.
- **Why:** retrying can't fix a 404 or a bad password; counting auth failures stops login hammering; permits stop slow calls from before an outage flipping the circuit.
- **Cost:** the circuit may stay open up to `reset_s` longer than strictly needed.

### ADR-014: Readings are register differences, attributed to the interval's start
- **Decision:** consumption for an interval `(prev, cur]` is the difference between consecutive cumulative registers. Hourly/daily buckets sum the intervals that *start* inside them. A negative kWh or kVAh difference is a register reset: the value is null, flagged, and excluded from totals. Any span longer than the detected interval (median spacing) is a gap, counting `ceil(span/interval) - 1` missing readings. Power factor is kWh/kVAh, flagged rather than clamped when above 1. A resolution finer than the meter's interval is rejected with 422.
- **Why:** the portal only exposes cumulative registers, so differences are the only honest consumption figure. Start-attribution puts a daily meter's 24 Jun→25 Jun reading on 24 Jun, which is the day it was used. Flagging data instead of "fixing" it keeps every quirk visible.
- **Cost:** a reading that is only slightly late counts as one missing interval. Hourly buckets on a 30-min meter hold two intervals each, so an hour with a reset under-reports its total.

### ADR-015: SQLite through SQLAlchemy Core, one transaction per request
- **Decision:** the local index is a single SQLite file, accessed with SQLAlchemy Core (no ORM) over `aiosqlite`. A linear Alembic chain migrates it at startup. Each request gets one connection inside one transaction, and repositories work on that connection, so a request commits or rolls back as a whole, and the commit happens before the response is sent. A partial unique index on `sync_runs(status) WHERE status='running'` makes "one sync at a time" a database guarantee. Runs left `running` by a crash are marked failed at startup.
- **Why:** 403 meters and ~100k readings fit comfortably in SQLite, so no server is needed; Core keeps each query visible and explainable. The driver's default transaction handling commits on a first-statement savepoint, so the engine issues `BEGIN` itself.
- **Cost:** a single writer at a time (fine for one sync plus reads in WAL mode); a meter's own DT code and its hierarchy DT code are stored in two columns (`dt_code`, `dt_node_code`), because the sources can disagree.

### ADR-016: Background sync, export first, paced to the portal's budget
- **Decision:** `POST /sync` records a run and returns 202, and a background task fills the index: the signed bulk export (or, if it fails, a crawl of search + detail + geo), then all transformer pages, then readings per meter (≤ 4 concurrent, each in its own transaction). Meters and DTs that vanished from the portal are deleted, unless the portal returned none. Per-meter reading failures are counted, not fatal. The index syncs automatically at startup when it is empty. Every portal request passes a pacer at 1.5 requests/s.
- **Why:** one export call replaces ~1,200 detail calls; a background run keeps the API responsive; the portal answers HTTP 429 (with no Retry-After) after ~120 requests in a short span, while 1–1.5 requests/s ran 400+ requests cleanly (PROTOCOL.md §5.1).
- **Cost:** a full sync with readings takes ~4.5 minutes; the pacing budget is shared with live API traffic, so a request during a sync may wait up to ~0.7 s.

### ADR-017: Meters are served from the index, falling back to the portal while it is empty
- **Decision:** `/meters` uses a `PreferIndexCatalog`: the SQLite index answers every query (combinable filters, sort, facets), and only while the index is empty does a plain search go to the live portal; anything that needs the index then answers 409 `index_not_ready`. Facet counts apply every filter except their own. Geo search prefilters on the `(lat, lng)` index with a bounding box, then sorts by exact haversine distance.
- **Why:** the portal can only do substring search 20 at a time; the index answers any combination in one query, and the fallback keeps the API useful during the first sync. Excluding a facet's own filter is what lets the UI show the alternatives next to the chosen chip.
- **Cost:** index answers are as old as the last sync (`meta.stale` after 24 h). A hierarchy-code filter matches the code wherever it occurs, since codes below zone level repeat; exact node filtering uses the hierarchy endpoints. Bounding-box prefiltering is comfortable to ~1M meters; beyond that use SQLite R-tree or PostGIS.
