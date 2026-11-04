import type { components } from "../generated/schema";

type S = components["schemas"];

export const meterSummary = (over: Partial<S["MeterSummary"]> = {}): S["MeterSummary"] => ({
  meter_id: "J100000",
  serial_no: "SE33962",
  make: "HPL",
  phase_type: "single",
  install_status: "installed",
  dt_code: "DT-001",
  ...over,
});

export const meterPage = (items: S["MeterSummary"][], over: Partial<S["Page_MeterSummary_"]> = {}): S["Page_MeterSummary_"] => ({
  items,
  page: 1,
  page_size: 25,
  total: items.length,
  total_pages: items.length ? 1 : 0,
  has_next: false,
  ...over,
});

export const meterDetail = (over: Partial<S["MeterDetail"]> = {}): S["MeterDetail"] => ({
  ...meterSummary(),
  install_type: "whole_current",
  build: "legacy",
  geo: null,
  hierarchy: [
    { level: "zone", code: "Z-01", name: "Jaipur Zone 1" },
    { level: "circle", code: "C-01", name: "Circle 1" },
    { level: "dt", code: "DT-001", name: "Malviya Nagar DT 1" },
  ],
  meta: { source: "portal", fetched_at: "2026-11-04T12:00:00Z", stale: false },
  ...over,
});

export const readingSeries = (over: Partial<S["ReadingSeriesResponse"]> = {}): S["ReadingSeriesResponse"] => ({
  meter_id: "J100000",
  resolution: "daily",
  interval_minutes: 30,
  interval_kind: "half_hourly",
  points: null,
  buckets: [
    {
      start: "2026-11-01T00:00:00+05:30",
      end: "2026-11-02T00:00:00+05:30",
      kwh: 12.5,
      kvah: 13,
      power_factor: 0.96,
      avg_voltage: 231.4,
      readings: 48,
      flags: [],
    },
  ],
  summary: {
    total_kwh: 12.5,
    total_kvah: 13,
    avg_voltage: 231.4,
    readings: 48,
    gaps: 2,
    resets: 1,
    first_at: "2026-11-01T00:30:00+05:30",
    last_at: "2026-11-02T00:00:00+05:30",
  },
  meta: { source: "portal", fetched_at: "2026-11-04T12:00:00Z", stale: false },
  ...over,
});

export const readiness = (over: Partial<S["ReadinessResponse"]> = {}): S["ReadinessResponse"] => ({
  status: "ready",
  portal: { breaker: "closed" },
  index: { ready: true, meter_count: 1234, last_sync_at: null },
  ...over,
});

export const errorBody = (code: string, message: string, details: Record<string, unknown> = {}) => ({
  error: { code, message, details },
});

export const facets = (over: S["FacetsResponse"]["facets"] = {}): S["FacetsResponse"] => ({
  facets: {
    status: { installed: 238, faulty: 90, decommissioned: 75 },
    make: { HPL: 200, Secure: 150, Genus: 53 },
    phase: { single: 277, three: 126, unknown: 0 },
    install_type: { whole_current: 300, ct_operated: 103 },
    dt: { "DT-007": 13, "DT-001": 20 },
    ...over,
  },
});

export const bboxMeter = (over: Partial<S["BBoxMeter"]> = {}): S["BBoxMeter"] => ({
  meter_id: "J100000",
  lat: 26.9,
  lng: 75.8,
  install_status: "installed",
  dt_code: "DT-001",
  ...over,
});

export const bboxResponse = (items: S["BBoxMeter"][], truncated = false): S["BBoxResponse"] => ({ items, truncated });

export const nearMeter = (distance_km: number, over: Partial<S["MeterSummary"]> = {}): S["NearMeter"] => ({
  meter: meterSummary(over),
  lat: 26.91,
  lng: 75.79,
  distance_km,
});

export const breakdown = (over: Partial<S["StatusBreakdown"]> = {}): S["StatusBreakdown"] => ({
  installed: 8,
  faulty: 1,
  decommissioned: 1,
  unknown: 0,
  ...over,
});

export const treeNode = (over: Partial<S["TreeNodeOut"]> = {}): S["TreeNodeOut"] => ({
  id: "Z-01",
  level: "zone",
  code: "Z-01",
  name: "Jaipur Zone 1",
  meter_count: 10,
  status_breakdown: breakdown(),
  unplaced_count: 0,
  children: [],
  ...over,
});

export const treeResponse = (items?: S["TreeNodeOut"][]): S["TreeResponse"] => ({
  items: items ?? [
    treeNode({
      children: [
        treeNode({ id: "Z-01/C-01", level: "circle", code: "C-01", name: "Circle 1", meter_count: 6, unplaced_count: 2 }),
      ],
    }),
    treeNode({ id: "Z-02", code: "Z-02", name: "Jaipur Zone 2", meter_count: 4, status_breakdown: breakdown({ installed: 4, faulty: 0, decommissioned: 0 }) }),
  ],
});

export const nodeDetail = (over: Partial<S["NodeDetailOut"]> = {}): S["NodeDetailOut"] => ({
  id: "Z-01/C-01",
  level: "circle",
  code: "C-01",
  name: "Circle 1",
  path: [
    { id: "Z-01", level: "zone", code: "Z-01", name: "Jaipur Zone 1", meter_count: 10 },
    { id: "Z-01/C-01", level: "circle", code: "C-01", name: "Circle 1", meter_count: 6 },
  ],
  children: [{ id: "Z-01/C-01/D-01", level: "division", code: "D-01", name: "Division 1", meter_count: 6 }],
  meter_count: 6,
  status_breakdown: breakdown({ installed: 5, faulty: 1, decommissioned: 0 }),
  unplaced_count: 0,
  alt_names: [],
  ...over,
});

export const consumption = (over: Partial<S["ConsumptionResponse"]> = {}): S["ConsumptionResponse"] => ({
  node: "Z-01/C-01",
  resolution: "daily",
  meters_included: 4,
  meters_excluded_coarser: 2,
  items: [{ start: "2026-11-01T00:00:00+05:30", end: "2026-11-02T00:00:00+05:30", kwh: 42, kvah: 44, meters: 4 }],
  ...over,
});

export const anomaly = (over: Partial<S["AnomalyOut"]> = {}): S["AnomalyOut"] => ({
  rule: "inactive_but_consuming",
  severity: "warning",
  meter_id: "J100000",
  message: "Marked decommissioned but still reporting",
  at: null,
  evidence: {},
  ...over,
});

export const anomalyList = (items: S["AnomalyOut"][], over: Partial<S["AnomalyListResponse"]> = {}): S["AnomalyListResponse"] => ({
  items,
  page: 1,
  page_size: 10,
  total: items.length,
  total_pages: items.length ? 1 : 0,
  has_next: false,
  rules: [
    { id: "inactive_but_consuming", severity: "warning", description: "Decommissioned meters that still report" },
    { id: "consumption_spike", severity: "error", description: "Sudden jump in usage" },
  ],
  ...over,
});

export const summary = (over: Partial<S["FleetSummaryOut"]> = {}): S["FleetSummaryOut"] => ({
  total_meters: 403,
  meters_by_status: { installed: 238, faulty: 90, decommissioned: 75, unknown: 0 },
  reporting_meters: 380,
  silent_meters: 23,
  total_kwh: 123456.7,
  first_reading_at: "2026-10-01T00:00:00+05:30",
  last_reading_at: "2026-11-01T00:00:00+05:30",
  anomalies_by_rule: { inactive_but_consuming: 165, consumption_spike: 17 },
  interval_kinds: { half_hourly: 40, daily: 363, unknown: 0 },
  ...over,
});

export const dtItem = (over: Partial<S["DtLoadOut"]> = {}): S["DtLoadOut"] => ({
  code: "DT-001",
  name: "Malviya Nagar DT 1",
  capacity_kva: 100,
  meter_count: 13,
  half_hourly_meters: 1,
  skipped_gap_intervals: 0,
  peak_kva_est: 1.2,
  avg_kva_est: 0.5,
  peak_at: "2026-10-15T19:00:00+05:30",
  utilisation_pct: 1.2,
  overloaded: false,
  ...over,
});

export const dtLoad = (items: S["DtLoadOut"][]): S["TransformerLoadResponse"] => ({
  estimate_note: "Estimate from half-hourly meters only; daily meters are ignored.",
  items,
});

export const quality = (over: Partial<S["DataQualityResponse"]> = {}): S["DataQualityResponse"] => ({
  items: [],
  page: 1,
  page_size: 1,
  total: 0,
  total_pages: 0,
  has_next: false,
  summary: { name_conflict: 2, missing_geo: 0 },
  checks: [
    { id: "name_conflict", severity: "warning", description: "Nodes with conflicting names" },
    { id: "missing_geo", severity: "info", description: "Meters without coordinates" },
  ],
  ...over,
});

export const syncRun = (over: Partial<S["SyncRunOut"]> = {}): S["SyncRunOut"] => ({
  id: 1,
  status: "succeeded",
  strategy: "export",
  started_at: "2026-11-04T10:00:00Z",
  finished_at: "2026-11-04T10:05:00Z",
  counts: { meters: 403, readings: 1000 },
  error: null,
  ...over,
});

export const syncStatus = (latest: S["SyncRunOut"] | null = syncRun()): S["SyncStatusResponse"] => ({
  latest,
  last_successful: latest?.status === "succeeded" ? latest : null,
});
