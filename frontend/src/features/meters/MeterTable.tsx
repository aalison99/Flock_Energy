import { Link } from "react-router";
import { StatusBadge } from "./StatusBadge";
import type { MeterSummary } from "./types";

export function MeterTable({ items, busy = false }: { items: MeterSummary[]; busy?: boolean }) {
  const th = "px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500";
  const td = "px-3 py-2 text-sm text-slate-700";
  return (
    <div className={`overflow-x-auto rounded-lg border border-slate-200 bg-white ${busy ? "opacity-60" : ""}`}>
      <table aria-busy={busy} className="min-w-full divide-y divide-slate-200">
        <caption className="sr-only">Meters</caption>
        <thead className="bg-slate-50">
          <tr>
            <th scope="col" className={th}>Meter</th>
            <th scope="col" className={th}>Serial</th>
            <th scope="col" className={th}>Make</th>
            <th scope="col" className={th}>Phase</th>
            <th scope="col" className={th}>Status</th>
            <th scope="col" className={th}>DT</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.map((m) => (
            <tr key={m.meter_id}>
              <td className={td}>
                <Link className="font-medium text-sky-700 hover:underline" to={`/meters/${m.meter_id}`}>
                  {m.meter_id}
                </Link>
              </td>
              <td className={td}>{m.serial_no}</td>
              <td className={td}>{m.make}</td>
              <td className={td}>{m.phase_type}</td>
              <td className={td}>
                <StatusBadge status={m.install_status} />
              </td>
              <td className={td}>{m.dt_code ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
