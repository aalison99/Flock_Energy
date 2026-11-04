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
