import { StatusBadge } from "./StatusBadge";
import type { MeterDetail } from "./types";

export function NameplateCard({ meter }: { meter: MeterDetail }) {
  const rows: [string, string][] = [
    ["Serial", meter.serial_no],
    ["Make", meter.make],
    ["Phase", meter.phase_type],
    ["Install type", meter.install_type ?? "—"],
    ["Build", meter.build ?? "—"],
    ["DT", meter.dt_code ?? "—"],
  ];
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">{meter.meter_id}</h1>
        <StatusBadge status={meter.install_status} />
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt>
            <dd className="text-slate-800">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
