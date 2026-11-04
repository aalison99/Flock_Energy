import { ApiError } from "../../lib/api-error";
import { formatDateTime } from "../../shared/format";
import { Loading } from "../../shared/ui/Loading";
import { SeverityBadge } from "../../shared/ui/SeverityBadge";
import { useMeterAnomalies } from "./hooks";

/** Compact anomaly list for one meter, shown above the readings chart. */
export function MeterAnomalies({ meterId }: { meterId: string }) {
  const { data, error, isPending, isError } = useMeterAnomalies(meterId);

  let body;
  if (isPending) body = <Loading label="Checking anomalies…" />;
  else if (isError) {
    const status = error instanceof ApiError ? error.status : 0;
    const text =
      status === 409
        ? "Anomaly checks are unavailable until the index has synced."
        : status === 404
          ? "No anomaly data for this meter."
          : `Could not load anomalies: ${error.message}`;
    body = <p role="alert" className="text-sm text-slate-600">{text}</p>;
  } else if (data.items.length === 0) body = <p className="text-sm text-slate-600">No anomalies detected</p>;
  else
    body = (
      <ul className="space-y-1.5">
        {data.items.map((a, i) => (
          <li key={`${a.rule}-${a.at ?? i}`} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm">
            <SeverityBadge severity={a.severity} />
            <span className="font-medium">{a.rule}</span>
            <span className="text-slate-700">{a.message}</span>
            {a.at ? <span className="text-xs text-slate-500">{formatDateTime(a.at)}</span> : null}
          </li>
        ))}
      </ul>
    );

  return (
    <section aria-labelledby="meter-anomalies-h" className="space-y-2 rounded-lg border border-slate-200 bg-white p-3">
      <h2 id="meter-anomalies-h" className="text-base font-semibold">Anomalies</h2>
      {body}
    </section>
  );
}
