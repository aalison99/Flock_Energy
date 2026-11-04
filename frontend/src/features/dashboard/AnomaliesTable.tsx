import { useEffect } from "react";
import { Link } from "react-router";
import { isConflict } from "../../lib/api-error";
import { formatDateTime } from "../../shared/format";
import { Empty } from "../../shared/ui/Empty";
import { ErrorState } from "../../shared/ui/ErrorState";
import { Loading } from "../../shared/ui/Loading";
import { Pagination } from "../../shared/ui/Pagination";
import { SeverityBadge } from "../../shared/ui/SeverityBadge";
import { useAnomalies } from "./hooks";
import { SEVERITIES } from "./types";
import type { AnomalyQuery } from "./types";

interface Props {
  query: AnomalyQuery;
  onChange: (patch: Partial<Record<"rule" | "severity" | "node" | "page", string>>) => void;
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-xs font-medium ${active ? "border-slate-900 bg-slate-900 text-white" : "border-slate-300 bg-white text-slate-700 hover:bg-slate-100"}`}
    >
      {children}
    </button>
  );
}

export function AnomaliesTable({ query, onChange }: Props) {
  const { data, error, isPending, isError, isPlaceholderData } = useAnomalies(query);
  const knownRules = data?.rules.map((r) => r.id) ?? [];
  const ruleChips = [...knownRules, ...(query.rule && !knownRules.includes(query.rule) ? [query.rule] : [])];
  const hasFilters = Boolean(query.rule || query.severity || query.node);

  // Once the server has told us which rules exist, an unknown rule in the URL is dropped.
  const unknownRule = Boolean(data && !isPlaceholderData && query.rule && !knownRules.includes(query.rule));
  useEffect(() => {
    if (unknownRule) onChange({ rule: "", page: "1" });
  }, [unknownRule, onChange]);
  const th = "px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500";
  const td = "px-3 py-2 text-sm text-slate-700 align-top";

  return (
    <section aria-labelledby="anomalies-h" className="space-y-3">
      <h2 id="anomalies-h" className="text-lg font-semibold">Anomalies</h2>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-500">Rule</span>
        {ruleChips.map((id) => (
          <span key={id} title={data?.rules.find((r) => r.id === id)?.description}>
            <Chip active={query.rule === id} onClick={() => onChange({ rule: query.rule === id ? "" : id, page: "1" })}>
              {id}
            </Chip>
          </span>
        ))}
        <span className="ml-2 text-xs text-slate-500">Severity</span>
        {SEVERITIES.map((s) => (
          <Chip key={s} active={query.severity === s} onClick={() => onChange({ severity: query.severity === s ? "" : s, page: "1" })}>
            {s}
          </Chip>
        ))}
        {query.node ? (
          <button
            type="button"
            className="rounded-full border border-sky-300 bg-sky-50 px-3 py-1 text-xs text-sky-800"
            onClick={() => onChange({ node: "", page: "1" })}
          >
            Node {query.node} ✕
          </button>
        ) : null}
        {hasFilters ? (
          <button type="button" className="text-xs text-sky-700 underline" onClick={() => onChange({ rule: "", severity: "", node: "", page: "1" })}>
            Clear filters
          </button>
        ) : null}
      </div>

      {isPending ? (
        <Loading label="Loading anomalies…" />
      ) : isError ? (
        <ErrorState title="Could not load anomalies" message={isConflict(error) ? "The index is empty — start a sync." : error.message} />
      ) : data.items.length === 0 ? (
        <Empty title="No anomalies match these filters" />
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="min-w-full divide-y divide-slate-200">
              <caption className="sr-only">Anomalies</caption>
              <thead className="bg-slate-50">
                <tr>
                  <th scope="col" className={th}>Severity</th>
                  <th scope="col" className={th}>Rule</th>
                  <th scope="col" className={th}>Meter</th>
                  <th scope="col" className={th}>Message</th>
                  <th scope="col" className={th}>At</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((a, i) => (
                  <tr key={`${a.meter_id}-${a.rule}-${a.at ?? i}`}>
                    <td className={td}><SeverityBadge severity={a.severity} /></td>
                    <td className={td}>{a.rule}</td>
                    <td className={td}>
                      <Link className="font-medium text-sky-700 hover:underline" to={`/meters/${a.meter_id}`}>{a.meter_id}</Link>
                    </td>
                    <td className={td}>{a.message}</td>
                    <td className={td}>{a.at ? formatDateTime(a.at) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={data.page}
            totalPages={data.total_pages}
            total={data.total}
            hasNext={data.has_next}
            onPageChange={(p) => onChange({ page: String(p) })}
          />
        </>
      )}
    </section>
  );
}
