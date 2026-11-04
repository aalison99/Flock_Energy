import { useState } from "react";
import { isConflict } from "../../lib/api-error";
import { ErrorState } from "../../shared/ui/ErrorState";
import { Loading } from "../../shared/ui/Loading";
import { SeverityBadge } from "../../shared/ui/SeverityBadge";
import { useQualityIssues, useQualitySummary } from "./hooks";

function Issues({ check }: { check: string }) {
  const { data, error, isPending, isError } = useQualityIssues(check, true);
  if (isPending) return <Loading label="Loading issues…" />;
  if (isError) return <ErrorState title="Could not load issues" message={error.message} />;
  return (
    <div className="space-y-2 px-3 pb-3">
      {data.total > data.items.length ? (
        <p className="text-xs text-slate-500">Showing {data.items.length} of {data.total}</p>
      ) : null}
      <ul className="space-y-2">
        {data.items.map((i, n) => (
          <li key={`${i.entity_id}-${n}`} className="rounded border border-slate-200 p-2 text-sm">
            <p>
              <span className="font-medium">{i.entity}</span> <span className="text-xs text-slate-500">{i.entity_id}</span>
            </p>
            <p className="text-slate-700">{i.message}</p>
            {Object.keys(i.evidence).length > 0 ? (
              <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 text-xs text-slate-600">
                {Object.entries(i.evidence).map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="font-medium">{k}</dt>
                    <dd className="break-words">{typeof v === "string" ? v : JSON.stringify(v)}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function DataQualityPanel() {
  const { data, error, isPending, isError } = useQualitySummary();
  const [open, setOpen] = useState<string | null>(null);

  return (
    <section aria-labelledby="dq-h" className="space-y-3">
      <h2 id="dq-h" className="text-lg font-semibold">Data quality</h2>
      {isPending ? (
        <Loading label="Loading data quality…" />
      ) : isError ? (
        <ErrorState title="Could not load data quality" message={isConflict(error) ? "The index is empty — start a sync." : error.message} />
      ) : (
        <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
          {data.checks.map((c) => {
            const count = data.summary[c.id] ?? 0;
            const expanded = open === c.id;
            return (
              <li key={c.id}>
                <button
                  type="button"
                  aria-expanded={expanded}
                  disabled={count === 0}
                  onClick={() => setOpen(expanded ? null : c.id)}
                  className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-slate-50 disabled:cursor-default disabled:hover:bg-white"
                >
                  <SeverityBadge severity={c.severity} />
                  <span className="font-medium">{c.id}</span>
                  <span className="text-slate-500">{c.description}</span>
                  <span className="ml-auto tabular-nums font-semibold">{count}</span>
                </button>
                {expanded ? <Issues check={c.id} /> : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
