import { Link } from "react-router";
import { Badge } from "../../shared/ui/Badge";
import { Empty } from "../../shared/ui/Empty";
import { ErrorState } from "../../shared/ui/ErrorState";
import { Loading } from "../../shared/ui/Loading";
import { Pagination } from "../../shared/ui/Pagination";
import { useNodeMeters } from "./hooks";

export function NodeMeters({ nodeId, page, onPageChange }: { nodeId: string; page: number; onPageChange: (p: number) => void }) {
  const { data, error, isPending, isError, isPlaceholderData } = useNodeMeters(nodeId, page);
  const th = "px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500";
  const td = "px-3 py-2 text-sm text-slate-700";

  return (
    <section className="space-y-2">
      <h3 className="text-base font-semibold">Meters in this node</h3>
      {isPending ? (
        <Loading label="Loading meters…" />
      ) : isError ? (
        <ErrorState title="Could not load meters" message={error.message} />
      ) : data.items.length === 0 ? (
        <Empty title="No meters in this node" />
      ) : (
        <>
          <div className={`overflow-x-auto rounded-lg border border-slate-200 bg-white ${isPlaceholderData ? "opacity-60" : ""}`}>
            <table aria-busy={isPlaceholderData} className="min-w-full divide-y divide-slate-200">
              <caption className="sr-only">Meters in this node</caption>
              <thead className="bg-slate-50">
                <tr>
                  <th scope="col" className={th}>Meter</th>
                  <th scope="col" className={th}>Make</th>
                  <th scope="col" className={th}>Status</th>
                  <th scope="col" className={th}>DT</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((m) => (
                  <tr key={m.meter_id}>
                    <td className={td}>
                      <Link className="font-medium text-sky-700 hover:underline" to={`/meters/${m.meter_id}`}>{m.meter_id}</Link>
                    </td>
                    <td className={td}>{m.make}</td>
                    <td className={td}>
                      <Badge tone={m.install_status === "unknown" ? "neutral" : m.install_status}>{m.install_status}</Badge>
                    </td>
                    <td className={td}>{m.dt_code ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={data.page} totalPages={data.total_pages} total={data.total} hasNext={data.has_next} onPageChange={onPageChange} />
        </>
      )}
    </section>
  );
}
