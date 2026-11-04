import { useCallback, useEffect } from "react";
import { isConflict } from "../../lib/api-error";
import { IndexSyncingNotice } from "../../shared/ui/IndexSyncingNotice";
import { Loading } from "../../shared/ui/Loading";
import { ErrorState } from "../../shared/ui/ErrorState";
import { useUrlState } from "../../shared/url-state";
import { AnomaliesTable } from "./AnomaliesTable";
import { DataQualityPanel } from "./DataQualityPanel";
import { DtLoadPanel } from "./DtLoadPanel";
import { useSummary } from "./hooks";
import { KpiTiles } from "./KpiTiles";
import { SyncPanel } from "./SyncPanel";
import { SEVERITIES } from "./types";

export function DashboardView() {
  const summary = useSummary();
  const [state, update] = useUrlState({ node: "", rule: "", severity: "", page: "1" });
  const severity = (SEVERITIES as string[]).includes(state.severity) ? state.severity : "";
  // An unknown severity in the URL is dropped from the URL and from the request.
  useEffect(() => {
    if (state.severity && !severity) update({ severity: "" }, { replace: true });
  }, [state.severity, severity, update]);
  const page = Math.max(1, Number.parseInt(state.page, 10) || 1);
  const onChange = useCallback((patch: Parameters<typeof update>[0]) => update(patch), [update]);

  return (
    <div className="space-y-8">
      <h1 className="text-xl font-semibold">What needs attention?</h1>

      {summary.isPending ? (
        <Loading label="Loading summary…" />
      ) : summary.isError && isConflict(summary.error) ? (
        <>
          <IndexSyncingNotice message={summary.error.message} />
          <SyncPanel />
        </>
      ) : summary.isError ? (
        <>
        <ErrorState title="Could not load the summary" message={summary.error.message}>
          <button type="button" className="rounded border border-red-300 bg-white px-3 py-1 text-sm hover:bg-red-100" onClick={() => void summary.refetch()}>
            Retry
          </button>
        </ErrorState>
        <SyncPanel />
        </>
      ) : (
        <>
          <KpiTiles summary={summary.data} />
          <AnomaliesTable query={{ node: state.node, rule: state.rule, severity, page }} onChange={onChange} />
          <div className="grid gap-8 lg:grid-cols-2">
            <DtLoadPanel />
            <DataQualityPanel />
          </div>
          <SyncPanel />
        </>
      )}
    </div>
  );
}
