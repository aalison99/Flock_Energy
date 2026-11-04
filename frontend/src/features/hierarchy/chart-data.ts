import type { Consumption } from "./types";

export interface ConsumptionRow {
  t: string;
  /** kWh of a bucket where every included meter reported. */
  full: number | null;
  /** kWh of a bucket where fewer meters than `meters_included` reported. */
  partial: number | null;
  meters: number;
  included: number;
}

/** A bucket is partial when fewer meters reported in it than the node has included meters. */
export function toConsumptionRows(data: Pick<Consumption, "items" | "meters_included">): ConsumptionRow[] {
  return data.items.map((b) => {
    const isPartial = b.meters < data.meters_included;
    return {
      t: b.start,
      full: isPartial ? null : b.kwh,
      partial: isPartial ? b.kwh : null,
      meters: b.meters,
      included: data.meters_included,
    };
  });
}
