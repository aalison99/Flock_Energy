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
