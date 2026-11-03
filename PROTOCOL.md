# PROTOCOL: how the Urja Meter Ops portal actually works

This describes the legacy portal at `https://urja-ops.flockenergy.tech` as I found it by exploring it as a normal logged-in user, between 3 and 5 Nov 2026. It covers what data exists, how to get it, how auth works, and the quirks to be careful of. Everything here was observed directly. Anything I could not confirm is marked **Unknown**, together with how our client copes with it.

Sanitised captures of every response below live in [`backend/tests/fixtures/portal/`](backend/tests/fixtures/portal/).

---

## 1. The short version

- The portal is a **SvelteKit** app. The HTML pages are thin: the browser fetches JSON from a small set of internal endpoints under `/portal/*`, plus SvelteKit's own `__data.json` route data. Our client talks to those JSON endpoints directly. It never scrapes HTML.
- **Auth** is a cookie session (better-auth). You log in by posting a form; the session cookie lasts **1 hour**.
- There are **five data sources**: meter search/list, meter detail (route data), meter geo, meter energy readings, and the distribution transformer (DT) list. There is also a **signed bulk export** that returns every meter, with hierarchy and location, in one call.
- The data is **messy on purpose**: two different meter-detail formats, two reading intervals, hierarchy codes that are only unique under their parent, blank hierarchy fields, and a transformer with two names.

---

## 2. Authentication

### Logging in
```
POST /login
Content-Type: application/x-www-form-urlencoded
Origin: https://urja-ops.flockenergy.tech        ← required (see below)
x-sveltekit-action: true                        ← asks SvelteKit for a JSON reply
Accept: application/json

email=<email>&password=<password>
```
| Outcome | HTTP | Body |
|---|---|---|
| Success | 200 | `{"type":"redirect","status":303,"location":"/meters"}` plus `Set-Cookie` |
| Wrong password | **200** (not 401) | `{"type":"failure","status":401,"data":"[…,\"Invalid email or password.\"]"}` |
| No `Origin` header | 403 | `{"message":"Cross-site POST form submissions are forbidden"}` |

- **Session cookie:** `__Secure-better-auth.session_token`, with `Max-Age=3600`, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`.
- **CSRF:** there is no token. SvelteKit's built-in protection only checks that `Origin` matches the site, so our client must send `Origin`.
- **Lifetime:** 1 hour, per the cookie. I confirmed this on the server side: a browser session from the afternoon was redirected to `/login` that evening. **Unknown:** whether activity extends the session ("sliding" expiry). Our client doesn't depend on that, because it re-logs in whenever it sees an expired-session signal (below).
- **Multiple sessions** are allowed. Logging in again issues a new cookie, and the old cookie keeps working.
- **Sign out:** `POST /api/auth/sign-out` (better-auth's standard route). Our client doesn't need it, but uses it on shutdown to be tidy.
- **Wrong password detection:** look for `"type":"failure"` in the body, not at the HTTP status. The status is 200 either way.

### What an expired or missing session looks like
Each kind of endpoint signals it differently, so the client must recognise all three:
| Endpoint kind | No / invalid session |
|---|---|
| `/portal/*` JSON | `401 {"error":"unauthorized","message":"A valid session is required."}` |
| `/…/__data.json` route data | **200** `{"type":"redirect","location":"/login"}` |
| HTML pages | `302 Location: /login` |

Our client treats any of the three as "session expired": it logs in again once and replays the request.

---

## 3. Data endpoints

All `/portal/*` endpoints return `application/json`. No caching headers were observed on them; route data sends `cache-control: private, no-store`. Typical latency is about 100–150 ms, and about 250 ms for the export.

### 3.1 Meter list / search: `GET /portal/meters/search?q=<text>&page=<n>`
```json
{"data":[{"meterId":"J100000","serialNo":"SE33962","make":"HPL","phaseType":"single",
          "installStatus":"Decommissioned","dtCode":"DT-001"}, …],
 "total":403,"page":1,"pageSize":20}
```
- **Page size is fixed at 20.** `pageSize`, `page_size` and `limit` are ignored. 403 meters → 21 pages.
- **Out-of-range pages:** `page=0`, `-1` and `abc` all silently return page 1. A page past the end (`22`) returns `data: []`, with the true `total` still set.
- **`q` matching:** case-insensitive *substring* match on **meter ID and serial number only**. `0001` matches J100001 and J100010–J100019; `se33962` matches `SE33962`. Make, status and DT code are **not** searched (`HPL`, `Installed` and `DT-007` all return 0).
- An empty or missing `q` lists everything.
- With a query, `total` is the **number of matches** (e.g. `q=SE3` → `total: 8`), so paging works the same for filtered results.

### 3.2 Meter detail: `GET /meters/<meterId>/__data.json`
This is SvelteKit route data, not a REST endpoint. Its shape is `{"type":"data","nodes":[layout, user, page]}`. The page node uses **devalue** encoding: `data` is a flat array, and objects refer to other entries by **index**. For example, `{"meterId":1}` means "the value at index 1".

Decoded, a meter has `meterId`, `detail` and `hierarchy`. `detail` comes in **two formats**, matching the export's `build` field:

| `build` | `detail` shape | Count |
|---|---|---|
| `legacy` | `{"data":[{"parameterName":"Serial No","parameterValue":"SE33962"}, …]}`: a list of label/value pairs (Meter ID, Serial No, Make, Phase Type, Installation Status, Installation Type) | 238 |
| `v2` | `{"classData":"{\"installed_meter\":{\"MeterId\":…,\"SerialNo\":…,\"Make\":…,\"PhaseType\":…,\"InstallationStatus\":…,\"InstallationType\":…}}"}`: a **JSON string inside JSON**, with PascalCase keys | 165 |

`hierarchy` is the same in both formats: a flat map whose values are `"<name> (<code>)"` strings, e.g. `"Zone":"Jaipur Zone 1 (Z-01)"`, through `"Circle"`, `"Division"`, `"Subdivision"`, `"Sub Station"`, `"Feeder"`, `"DT"`.

- **Unknown meter:** HTTP **200**, with the page node set to `{"type":"error","error":{"message":"Meter not found"},"status":404}`. The real status is inside the body.
- **No session:** 200 `{"type":"redirect","location":"/login"}` (see §2).

### 3.3 Meter location: `GET /portal/meters/<meterId>/geo`
`{"data":{"latitude":"26.938961002479868","longitude":"75.83095696146852"}}`. The coordinates are **strings**. Unknown meter → `404 {"error":"not_found","message":"Meter not found"}`.

### 3.4 Meter readings: `GET /portal/meters/<meterId>/energy[?from=YYYY-MM-DD&to=YYYY-MM-DD]`
```json
{"data":[{"timestamp":"23/06/2026 23:30","kwh":"48438.74","kvah":"52313.84","voltR":"226"}, …]}
```
- **The values are cumulative register readings**, not consumption. Consumption for an interval is the difference between consecutive readings. Every number is a **string**.
- **Timestamps** are `dd/mm/yyyy HH:MM` with **no timezone**. I assume IST (Asia/Kolkata): the utility is in Jaipur, and the readings line up with local midnight.
- **Two intervals exist:** some meters report **every 30 minutes** (337 points over the window), others **once a day** at 00:00 (8 points). The interval doesn't follow `build`, install type or status in the sample I checked, so **our client detects the interval from the timestamps** instead of assuming it.
- **Window:** 23/06/2026 to 30/06/2026. The latest reading is 30/06/2026 23:30, months before "today". The portal holds a fixed snapshot, not live data.
- **Date filter:** `from` / `to` (inclusive calendar days) **are honoured**: `from=2026-06-29&to=2026-06-30` returns 96 half-hourly points. Other names (`start`/`end`, `days`, `page`) are ignored, and the full window is returned.
- **Only phase R voltage** (`voltR`) is exposed, even for three-phase meters.
- Unknown meter → `404 not_found`.

### 3.5 Distribution transformers: `GET /portal/dts?page=<n>`
`{"data":[{"code":"DT-001","name":"Malviya Nagar DT 1","feederCode":"F-001","capacityKva":100}, …],"total":40,"page":1,"pageSize":20}`. This is the only endpoint with real numbers (`capacityKva`). It has the same fixed paging of 20, and 40 DTs means 2 pages.

### 3.6 The bulk export: `GET /portal/export?page=1` (signed)
This sits behind the "Export all meters" button on the Transformers page. It returns **all 403 meters in one response**, each with full hierarchy objects and numeric geo:
```json
{"data":[{"meterId":"J100000","serialNo":"SE33962","make":"HPL","phaseType":"single",
          "installStatus":"Decommissioned","installType":"Whole Current","build":"legacy",
          "dtCode":"DT-001",
          "hierarchy":{"zone":{"name":"Jaipur Zone 1","code":"Z-01"}, …, "dt":{"name":"Malviya Nagar DT 1","code":"DT-001"}},
          "geo":{"lat":26.938961002479868,"lng":75.83095696146852}}, …],
 "total":403}
```
The request must be **signed**. I found the scheme in the page's own JavaScript and verified it byte for byte against a real browser request:
1. `GET /portal/keys` → `{"data":{"signingSecret":"…"}}` (available to any logged-in user).
2. Build the message from four lines joined with `\n`: method, path, query, Unix time in seconds:
   ```
   GET
   /portal/export
   page=1
   1793697409
   ```
3. Compute `x-signature` = lowercase hex of HMAC-SHA256(secret, message), and set `x-timestamp` = the same Unix seconds.
4. Send both as headers.

- Missing or invalid signature → `401 {"error":"signature_invalid","message":"Missing or invalid request signature."}`.
- The secret was the **same** across calls and across separate logins during exploration. **Unknown:** whether it ever rotates. Our client fetches it fresh before every export and refetches once if a signature is rejected.
- `page=2` returns exactly the same 403 records as `page=1`. The parameter is accepted but there is only one page, so our client stops when it has `total` records.
- **Unknown (deliberately not probed):** how old a timestamp may be. Testing that would mean probing a security control. Our client always signs at send time, so it doesn't matter.
- This one call replaces the roughly 1,200 per-meter calls (search + detail + geo) needed to build the same dataset.

### 3.7 Other routes
- `GET /meters/__data.json` and the layout node in every route-data reply contain only the logged-in user (`{"name":"Ops Desk","email":…}`).
- No rate limiting was seen: 109 sequential requests in about 1 minute produced no 429s and no rate-limit headers. Our client stays polite anyway (sequential by default, at most 4 concurrent during sync, backoff on errors).

---

## 4. The data model, and where it's messy

### 4.1 The network hierarchy
`Zone → Circle → Division → Subdivision → Substation → Feeder → DT → Meter`, about 3 / 6 / 30 / 40 / 40 / 40 / 40 nodes, with 403 meters.

**Surprise: codes are only unique under their parent.** `D-01` appears under circles C-01, C-03 and C-05. `SS-01` appears under three subdivisions. `F-001` appears under two substations. Read globally, the codes would make a tangled graph. Once each node is identified by its **full code path** (e.g. `Z-01/C-01/D-07/…/DT-007`), the data forms a clean tree with exactly one name per path. Our API therefore uses the path as the node ID.
- **DT codes are the exception**: `DT-001`…`DT-040` are globally unique, and every one has meters.
- The DT list's `feederCode` covers only `F-001`…`F-028`. On its own it is ambiguous, because a feeder code repeats across substations. The DT's position in the tree has to come from its meters' hierarchy paths.

### 4.2 Data quality issues found (complete list for this dataset)
| Issue | Where | How we handle it |
|---|---|---|
| **One DT, two names** | DT-007 is "Sanganer DT 7" in the DT list and for 10 meters, but "Old Malviya Nagar Xfmr" for 3 meters (J100400–J100402) | The DT list name is canonical. The other name is kept as an alias and reported in `/data-quality`. |
| Those 3 meters also stand out | J100400–402 are the last IDs, and the only `GN…` serials | Reported as related evidence. They look like a later import. |
| **Blank hierarchy fields** | 22 meters each have one level with an empty `code` *or* an empty `name` (circle, substation or feeder) | Repaired from the other half using the number rule (name "Circle 6" ↔ code "C-06"; this rule held for every non-blank pair) or from the path's canonical name. Each repair is reported, with before/after values. |
| Install status vs readings | Decommissioned and faulty meters still show increasing kWh registers (e.g. J100000) | Not "fixed". Surfaced as an anomaly. |
| Two detail formats | `legacy` vs `v2` (§3.2) | One parser per format, via a registry. |
| Two reading intervals | 30-min vs daily (§3.4) | Interval detected per series. |
| Strings for numbers | geo, kWh, kVAh, voltage | Converted to numbers at the edge. |
| Lying HTTP statuses | Wrong password and unknown meter (route data) return 200 | The body is checked, not just the status. |
| Serial prefixes | `SE`, `GE`, `AL`, `L&`, `HP`, `GN` don't correspond to the make (e.g. `SE…` serials occur across all five makes) | Treated as opaque strings. We don't validate make from serial. |

What was **consistent**:
- The search list and the export agree on every field for all 403 meters.
- `dtCode` always matches `hierarchy.dt.code`.
- Every meter has geo, all inside Jaipur (lat 26.79–27.04, lng 75.66–75.91).
- There are no duplicate IDs or serials.
- Geo from the geo endpoint matches the export for every meter sampled.

### 4.3 Enumerations seen
| Field | Values (count) |
|---|---|
| make | HPL 90, Genus 88, Secure 85, Allied 76, L&T 64 |
| phaseType | single 277, three 126 |
| installStatus | Installed 238, Faulty 90, Decommissioned 75 |
| installType | Whole Current 205, CT Operated 198 (only in detail/export, not in search) |
| build | legacy 238, v2 165 (export only) |

---

## 5. How our client uses this

| Need | Path we use | Why |
|---|---|---|
| Full meter dataset (sync) | Signed bulk export | 1 call instead of ~1,200 |
| Fallback if the export fails | search (21 pages) + detail + geo per meter, ≤ 4 concurrent | The same data, assembled by hand |
| Transformers | `/portal/dts` (2 pages) | The only source of capacity |
| Readings | `/portal/meters/<id>/energy`, with `from`/`to` when the caller gives a range | The only source of readings |
| Session upkeep | Re-login on any of the three expiry signals; one re-login at a time | The cookie lasts 1 hour, and long syncs or long-running servers outlive it |

## 6. Open questions (still unknown)
- Whether the session expiry slides with activity. *Handled: we re-login on expiry.*
- Whether `signingSecret` ever rotates. *Handled: fetched fresh for each export, refetched once on rejection.*
- What decides a meter's reading interval. *Handled: detected per series.* This will be checked across all 403 meters during the first full sync.
- What `build: v2` means operationally. It looks like a newer meter-data system, judging by its JSON-in-JSON `classData`. *Handled: one parser per format.*

## 7. How this was discovered
1. Logged in through the UI with browser network capture on, and recorded every request each page makes.
2. Read the Transformers page's JavaScript to find how the export button signs its request, then reproduced the signature offline and checked it against the browser's.
3. Ran a small sequential probe script (109 GETs and form posts, 0.4 s apart) covering no-session, invalid-session, unknown-ID, search, paging, date-range and export cases.
4. Compared the export, all 21 search pages, both DT pages, and a sample of detail, geo and energy responses field by field, to find the inconsistencies above.

Not done, on purpose: brute-forcing, malformed or bad signatures, timestamp-window probing, load testing, or anything a normal logged-in user couldn't do.
