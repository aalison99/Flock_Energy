import { useMemo } from "react";
import { Link } from "react-router";
import { isConflict } from "../../lib/api-error";
import { Empty } from "../../shared/ui/Empty";
import { ErrorState } from "../../shared/ui/ErrorState";
import { IndexSyncingNotice } from "../../shared/ui/IndexSyncingNotice";
import { Loading } from "../../shared/ui/Loading";
import { useUrlState } from "../../shared/url-state";
import { useNameConflicts, useNode, useTree } from "./hooks";
import { NodeDetail } from "./NodeDetail";
import { TreeList } from "./Tree";
import type { ConsumptionResolution } from "./types";

const NO_CONFLICTS = new Set<string>();
const NO_IDS = new Set<string>();

export function HierarchyExplorer() {
  const [state, update] = useUrlState({ node: "", res: "daily", mpage: "1" });
  const tree = useTree();
  const conflicts = useNameConflicts().data ?? NO_CONFLICTS;
  // Shares the detail panel's query; its path tells the tree which ancestors to open.
  const selected = useNode(state.node, Boolean(state.node)).data;
  const openIds = useMemo(() => (selected ? new Set(selected.path.slice(0, -1).map((p) => p.id)) : NO_IDS), [selected]);
  const resolution: ConsumptionResolution = state.res === "hourly" ? "hourly" : "daily";
  const meterPage = Math.max(1, Number.parseInt(state.mpage, 10) || 1);

  return (
    <section className="space-y-4">
      <h1 className="text-xl font-semibold">Hierarchy</h1>
      {tree.isPending ? (
        <Loading label="Loading hierarchy…" />
      ) : tree.isError ? (
        isConflict(tree.error) ? (
          <IndexSyncingNotice message={tree.error.message}>
            <Link className="text-sky-700 underline" to="/">Go to the dashboard to start a sync</Link>
          </IndexSyncingNotice>
        ) : (
          <ErrorState title="Could not load the hierarchy" message={tree.error.message}>
            <button type="button" className="rounded border border-red-300 bg-white px-3 py-1 text-sm hover:bg-red-100" onClick={() => void tree.refetch()}>
              Retry
            </button>
          </ErrorState>
        )
      ) : tree.data.items.length === 0 ? (
        <Empty title="No hierarchy yet">Start a sync from the dashboard.</Empty>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(18rem,24rem)_1fr]">
          <nav aria-label="Hierarchy tree" className="max-h-[75vh] overflow-y-auto rounded-lg border border-slate-200 bg-white p-2">
            <TreeList
              nodes={tree.data.items}
              selectedId={state.node}
              openIds={openIds}
              conflicts={conflicts}
              onSelect={(node) => update({ node, mpage: "1" })}
            />
          </nav>
          <div>
            {state.node ? (
              <NodeDetail
                nodeId={state.node}
                resolution={resolution}
                meterPage={meterPage}
                conflict={conflicts.has(state.node)}
                onSelectNode={(node) => update({ node, mpage: "1" })}
                onResolution={(res) => update({ res })}
                onMeterPage={(p) => update({ mpage: String(p) })}
              />
            ) : (
              <Empty title="Select a node">Pick a zone, circle or transformer on the left.</Empty>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
