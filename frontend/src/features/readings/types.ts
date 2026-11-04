import type { components } from "../../generated/schema";

export type Resolution = components["schemas"]["Resolution"];
export type ReadingSeries = components["schemas"]["ReadingSeriesResponse"];

export const RESOLUTIONS: Resolution[] = ["raw", "hourly", "daily"];

export interface ChartPoint {
  t: string;
  kwh: number | null;
  voltage: number | null;
}
