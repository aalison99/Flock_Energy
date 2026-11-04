import { lazy, Suspense } from "react";
import { isConflict } from "../../lib/api-error";
import { formatNumber } from "../../shared/format";
import { Badge } from "../../shared/ui/Badge";
import { Empty } from "../../shared/ui/Empty";
import { ErrorState } from "../../shared/ui/ErrorState";
import { Loading } from "../../shared/ui/Loading";
import { useDtLoad } from "./hooks";

const DtLoadChart = lazy(() => import("./DtLoadChart"));

export function DtLoadPanel() {
  const { data, error, isPending, isError } = useDtLoad();
  return (
    <section aria-labelledby="dt-h" className="space-y-3">
      <h2 id="dt-h" className="text-lg font-semibold">
        Transformer utilisation <Badge tone="info">estimate</Badge>
      </h2>
      {isPending ? (
        <Loading label="Loading transformer load…" />
      ) : isError ? (
        <ErrorState title="Could not load transformer load" message={isConflict(error) ? "The index is empty — start a sync." : error.message} />
      ) : (
        (() => {
          const withEstimate = data.items.filter((i) => i.utilisation_pct !== null);
          const without = data.items.filter((i) => i.utilisation_pct === null);
          return (
            <>
              {withEstimate.length === 0 ? (
                <Empty title="No transformer has a load estimate" />
              ) : (
                <>
                  <Suspense fallback={<Loading label="Loading chart…" />}>
                    <DtLoadChart items={withEstimate} />
                  </Suspense>
                  <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
                    <table className="min-w-full divide-y divide-slate-200 text-sm">
                      <caption className="sr-only">Top transformers by estimated utilisation</caption>
                      <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                        <tr>
                          <th scope="col" className="px-3 py-2 text-left">DT</th>
                          <th scope="col" className="px-3 py-2 text-right">Utilisation (est.)</th>
                          <th scope="col" className="px-3 py-2 text-right">Peak kVA (est.)</th>
                          <th scope="col" className="px-3 py-2 text-right">Capacity kVA</th>
                          <th scope="col" className="px-3 py-2 text-right">Coverage</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {withEstimate.map((i) => (
                          <tr key={i.code}>
                            <td className="whitespace-nowrap px-3 py-1.5">
                              {i.code} {i.overloaded ? <Badge tone="danger">overloaded</Badge> : null}
                            </td>
                            <td className="px-3 py-1.5 text-right tabular-nums">{formatNumber(i.utilisation_pct ?? 0, 2)}%</td>
                            <td className="px-3 py-1.5 text-right tabular-nums">{i.peak_kva_est === null ? "—" : formatNumber(i.peak_kva_est, 2)}</td>
                            <td className="px-3 py-1.5 text-right tabular-nums">{i.capacity_kva}</td>
                            <td className="px-3 py-1.5 text-right tabular-nums">
                              {i.half_hourly_meters} of {i.meter_count} meters
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
              {without.length > 0 ? (
                <div className="text-sm text-slate-600">
                  <p className="font-medium">No half-hourly meters</p>
                  <p>{without.map((i) => i.code).join(", ")}</p>
                </div>
              ) : null}
              <p className="text-xs text-slate-500">{data.estimate_note}</p>
            </>
          );
        })()
      )}
    </section>
  );
}
