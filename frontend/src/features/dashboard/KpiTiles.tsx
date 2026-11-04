import { formatDateTime, formatNumber } from "../../shared/format";
import { Badge } from "../../shared/ui/Badge";
import type { Summary } from "./types";

function Tile({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm text-slate-800">{children}</dd>
    </div>
  );
}

export function KpiTiles({ summary }: { summary: Summary }) {
  const s = summary;
  const window =
    s.first_reading_at && s.last_reading_at ? `${formatDateTime(s.first_reading_at)} to ${formatDateTime(s.last_reading_at)}` : "No readings yet";
  return (
    <dl aria-label="Key figures" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Tile label="Meters">
        <p className="text-2xl font-semibold tabular-nums">{s.total_meters.toLocaleString("en-IN")}</p>
        <p className="mt-1 flex flex-wrap gap-1">
          <Badge tone="installed">{`${s.meters_by_status.installed} installed`}</Badge>
          <Badge tone="faulty">{`${s.meters_by_status.faulty} faulty`}</Badge>
          <Badge tone="decommissioned">{`${s.meters_by_status.decommissioned} decommissioned`}</Badge>
          {s.meters_by_status.unknown > 0 ? <Badge>{`${s.meters_by_status.unknown} unknown`}</Badge> : null}
        </p>
      </Tile>
      <Tile label="Reporting">
        <p className="text-2xl font-semibold tabular-nums">{s.reporting_meters.toLocaleString("en-IN")}</p>
        <p className="mt-1 text-slate-600">{s.silent_meters.toLocaleString("en-IN")} silent (fewer than 2 readings)</p>
      </Tile>
      <Tile label="Energy in window">
        <p className="text-2xl font-semibold tabular-nums">{formatNumber(s.total_kwh, 0)} kWh</p>
        <p className="mt-1 text-slate-600">{window}</p>
      </Tile>
      <Tile label="Reading cadence">
        <ul className="space-y-0.5">
          {Object.entries(s.interval_kinds).map(([kind, n]) => (
            <li key={kind}>
              {kind.replace("_", "-")}: <span className="tabular-nums font-medium">{n.toLocaleString("en-IN")}</span>
            </li>
          ))}
        </ul>
      </Tile>
    </dl>
  );
}

