import { lazy, Suspense } from "react";
import { Link } from "react-router";
import { ApiError } from "../../lib/api-error";
import { Badge } from "../../shared/ui/Badge";
import { Empty } from "../../shared/ui/Empty";
import { ErrorState } from "../../shared/ui/ErrorState";
import { Loading } from "../../shared/ui/Loading";
import { formatNumber } from "../../shared/format";
import { BreakdownBar } from "./BreakdownBar";
import { useConsumption, useNode, useNodeAnomalyTotal } from "./hooks";
import { NodeMeters } from "./NodeMeters";
import type { ConsumptionResolution } from "./types";

const ConsumptionChart = lazy(() => import("./ConsumptionChart"));

interface Props {
  nodeId: string;
  resolution: ConsumptionResolution;
  meterPage: number;
  conflict: boolean;
  onSelectNode: (id: string) => void;
  onResolution: (r: ConsumptionResolution) => void;
  onMeterPage: (p: number) => void;
}

function Consumption({ nodeId, resolution, onResolution }: { nodeId: string; resolution: ConsumptionResolution; onResolution: (r: ConsumptionResolution) => void }) {
  const { data, error, isPending, isError } = useConsumption(nodeId, resolution);
  const btn = (r: ConsumptionResolution) =>
    `rounded px-3 py-1 text-sm ${resolution === r ? "bg-slate-900 text-white" : "border border-slate-300 bg-white text-slate-700"}`;
  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold">Consumption</h3>
        <div role="group" aria-label="Resolution" className="flex gap-1">
          {(["daily", "hourly"] as const).map((r) => (
            <button key={r} type="button" aria-pressed={resolution === r} className={btn(r)} onClick={() => onResolution(r)}>
              {r === "daily" ? "Daily" : "Hourly"}
            </button>
          ))}
        </div>
      </div>
      {isPending ? (
        <Loading label="Loading consumption…" />
      ) : isError ? (
        <ErrorState title="Could not load consumption" message={error.message} />
      ) : (
        <>
          <p className="text-xs text-slate-500">
            {data.meters_included} meters included
            {data.meters_excluded_coarser > 0 ? `, ${data.meters_excluded_coarser} excluded (readings coarser than ${resolution})` : ""}
          </p>
          {data.items.length === 0 ? (
            <Empty title="No consumption data for this node" />
          ) : (
            <Suspense fallback={<Loading label="Loading chart…" />}>
              <ConsumptionChart data={data} />
            </Suspense>
          )}
        </>
      )}
    </section>
  );
}

function AnomalyLink({ nodeId }: { nodeId: string }) {
  const { data, isPending, isError } = useNodeAnomalyTotal(nodeId);
  if (isPending) return <span className="text-sm text-slate-500">Checking anomalies…</span>;
  if (isError) return <span className="text-sm text-slate-500">Anomaly count unavailable</span>;
  const search = new URLSearchParams({ node: nodeId }).toString();
  return (
    <Link className="text-sm text-sky-700 hover:underline" to={{ pathname: "/", search }}>
      {data === 0 ? "No anomalies" : `${data} ${data === 1 ? "anomaly" : "anomalies"}`} · view on dashboard
    </Link>
  );
}

export function NodeDetail({ nodeId, resolution, meterPage, conflict, onSelectNode, onResolution, onMeterPage }: Props) {
  const { data: node, error, isPending, isError } = useNode(nodeId);

  if (isPending) return <Loading label="Loading node…" />;
  if (isError) {
    if (error instanceof ApiError && error.status === 404) return <Empty title="Node not found">No node with id {nodeId}.</Empty>;
    return <ErrorState title="Could not load node" message={error.message} />;
  }

  return (
    <div className="space-y-5">
      <nav aria-label="Node path" className="text-sm text-slate-500">
        <ol className="flex flex-wrap items-center gap-1">
          {node.path.map((p, i) => (
            <li key={p.id} className="flex items-center gap-1">
              {i > 0 ? <span aria-hidden="true">›</span> : null}
              {p.id === node.id ? (
                <span aria-current="page" className="font-medium text-slate-800">{p.name}</span>
              ) : (
                <button type="button" className="text-sky-700 hover:underline" onClick={() => onSelectNode(p.id)}>{p.name}</button>
              )}
            </li>
          ))}
        </ol>
      </nav>

      <div className="space-y-2">
        <h2 className="text-lg font-semibold">
          {node.name} <span className="text-sm font-normal text-slate-500">{node.code} · {node.level}</span>
        </h2>
        <p className="text-sm text-slate-600">{formatNumber(node.meter_count, 0)} meters in this node and below</p>
        <BreakdownBar breakdown={node.status_breakdown} />
        <div className="flex flex-wrap items-center gap-2">
          {node.unplaced_count > 0 ? <Badge tone="faulty">{`${node.unplaced_count} unplaced`}</Badge> : null}
          {conflict ? <Badge tone="faulty">name conflict</Badge> : null}
          {node.alt_names.map((a) => (
            <span key={a.name} title={a.meter_ids.join(", ")}>
              <Badge tone="info">also called {a.name}</Badge>
              <span className="ml-1 text-xs text-slate-500">({a.meter_ids.join(", ")})</span>
            </span>
          ))}
        </div>
        <AnomalyLink nodeId={node.id} />
      </div>

      <Consumption nodeId={node.id} resolution={resolution} onResolution={onResolution} />
      <NodeMeters nodeId={node.id} page={meterPage} onPageChange={onMeterPage} />
    </div>
  );
}
