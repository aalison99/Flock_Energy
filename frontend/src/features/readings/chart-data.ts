import type { ChartPoint, ReadingSeries } from "./types";

/** Flatten raw points or aggregated buckets into one shape the chart can draw. */
export function toChartPoints(series: ReadingSeries): ChartPoint[] {
  if (series.points) {
    return series.points.map((p) => ({ t: p.at, kwh: p.kwh, voltage: p.voltage_r }));
  }
  return (series.buckets ?? []).map((b) => ({ t: b.start, kwh: b.kwh, voltage: b.avg_voltage }));
}
