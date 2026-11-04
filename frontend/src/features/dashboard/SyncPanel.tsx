import { useEffect, useRef } from "react";
import { ApiError } from "../../lib/api-error";
import { formatDateTime } from "../../shared/format";
import { Badge } from "../../shared/ui/Badge";
import { ErrorState } from "../../shared/ui/ErrorState";
import { Loading } from "../../shared/ui/Loading";
import { useRefreshDashboard, useStartSync, useSyncStatus } from "./hooks";
import type { SyncRun } from "./types";

const TONE = { running: "info", succeeded: "installed", failed: "danger" } as const;

function RunSummary({ title, run }: { title: string; run: SyncRun }) {
  return (
    <div className="space-y-1 text-sm">
      <p className="flex items-center gap-2">
        <span className="font-medium">{title}</span>
        <Badge tone={TONE[run.status]}>{run.status}</Badge>
        {run.strategy ? <span className="text-slate-500">{run.strategy}</span> : null}
      </p>
      <p className="text-slate-600">
        Started {formatDateTime(run.started_at)}
        {run.finished_at ? `, finished ${formatDateTime(run.finished_at)}` : ""}
      </p>
      {run.error ? <p className="text-red-700">{run.error}</p> : null}
      {Object.keys(run.counts).length > 0 ? (
        <ul className="flex flex-wrap gap-x-3 text-xs text-slate-600">
          {Object.entries(run.counts).map(([k, v]) => (
            <li key={k}>{k.replace(/_/g, " ")}: <span className="tabular-nums">{v}</span></li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function SyncPanel() {
  const { data, error, isPending, isError } = useSyncStatus();
  const start = useStartSync();
  const refresh = useRefreshDashboard();
  const running = data?.latest?.status === "running";

  // When a run stops running, reload the panels that depend on the index.
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && data && !running) void refresh();
    wasRunning.current = running;
  }, [running, data, refresh]);

  const alreadyRunning = start.error instanceof ApiError && start.error.status === 409;

  return (
    <section aria-labelledby="sync-h" className="space-y-3">
      <h2 id="sync-h" className="text-lg font-semibold">Sync</h2>
      {isPending ? (
        <Loading label="Loading sync status…" />
      ) : isError ? (
        <ErrorState title="Could not load sync status" message={error.message} />
      ) : (
        <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-3">
          {data.latest ? <RunSummary title="Latest run" run={data.latest} /> : <p className="text-sm text-slate-600">No sync has run yet.</p>}
          <p className="text-sm text-slate-600">
            Last successful sync: {data.last_successful?.finished_at ? formatDateTime(data.last_successful.finished_at) : "never"}
          </p>
        </div>
      )}
      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={running || start.isPending}
          onClick={() => start.mutate()}
          className="rounded bg-slate-900 px-4 py-1.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          {running ? "Syncing…" : "Resync"}
        </button>
        {alreadyRunning ? (
          <p role="status" className="text-sm text-amber-800">A sync is already running.</p>
        ) : start.isError ? (
          <p role="alert" className="text-sm text-red-700">Could not start a sync: {start.error.message}</p>
        ) : null}
      </div>
    </section>
  );
}
