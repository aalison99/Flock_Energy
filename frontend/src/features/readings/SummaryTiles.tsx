import { formatNumber } from "../../shared/format";
import type { ReadingSeries } from "./types";

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-slate-900">{value}</p>
    </div>
  );
}

export function SummaryTiles({ series }: { series: ReadingSeries }) {
  const { summary } = series;
  const cadence =
    series.interval_minutes != null ? `${series.interval_kind} (${series.interval_minutes} min)` : series.interval_kind;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
      <Tile label="Total kWh" value={formatNumber(summary.total_kwh, 2)} />
      <Tile label="Avg voltage" value={summary.avg_voltage != null ? `${formatNumber(summary.avg_voltage)} V` : "—"} />
      <Tile label="Gaps" value={String(summary.gaps)} />
      <Tile label="Resets" value={String(summary.resets)} />
      <Tile label="Interval" value={cadence.replace("_", " ")} />
    </div>
  );
}
