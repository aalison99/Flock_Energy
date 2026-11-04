import { useEffect, useState } from "react";
import { Loading } from "../../shared/ui/Loading";
import { Badge } from "../../shared/ui/Badge";
import { BreakdownBar } from "./BreakdownBar";
import { useNode } from "./hooks";
import type { TreeRowNode } from "./types";

interface RowProps {
  node: TreeRowNode;
  selectedId: string;
  /** Ids on the path to the selected node; they open themselves (deep links). */
  openIds: Set<string>;
  conflicts: Set<string>;
  onSelect: (id: string) => void;
}

function TreeRow({ node, selectedId, openIds, conflicts, onSelect }: RowProps) {
  const [expanded, setExpanded] = useState(false);
  const forcedOpen = openIds.has(node.id);
  useEffect(() => {
    if (forcedOpen) setExpanded(true);
  }, [forcedOpen]);
  const preloaded = (node.children?.length ?? 0) > 0;
  const expandable = node.level !== "dt";
  const lazy = useNode(node.id, expanded && expandable && !preloaded);
  const children = preloaded ? node.children : lazy.data?.children;
  const selected = node.id === selectedId;

  return (
    <li>
      <div className={`flex items-start rounded hover:bg-slate-100 ${selected ? "bg-sky-50 ring-1 ring-sky-200" : ""}`}>
        {expandable ? (
          <button
            type="button"
            aria-expanded={expanded}
            aria-label={`${expanded ? "Collapse" : "Expand"} ${node.name}`}
            onClick={() => setExpanded((e) => !e)}
            className="w-6 shrink-0 py-1.5 text-slate-500"
          >
            <span aria-hidden="true">{expanded ? "▾" : "▸"}</span>
          </button>
        ) : (
          <span className="w-6 shrink-0" />
        )}
        <button
          type="button"
          aria-current={selected ? "true" : undefined}
          onClick={() => onSelect(node.id)}
          className="block min-w-0 flex-1 py-1.5 pr-2 text-left text-sm"
        >
          <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
            <span className="font-medium text-slate-800">{node.name}</span>
            <span className="text-xs text-slate-500">{node.code}</span>
            <span className="ml-auto text-xs tabular-nums text-slate-600">{node.meter_count.toLocaleString("en-IN")} meters</span>
          </span>
          <span className="mt-1 flex flex-wrap items-center gap-2">
            {node.status_breakdown ? (
              <span className="min-w-[4rem] flex-1">
                <BreakdownBar breakdown={node.status_breakdown} />
              </span>
            ) : null}
            {node.unplaced_count ? <Badge tone="faulty">{`${node.unplaced_count} unplaced`}</Badge> : null}
            {conflicts.has(node.id) ? <Badge tone="faulty">name conflict</Badge> : null}
          </span>
        </button>
      </div>
      {expanded && expandable ? (
        <div className="ml-4 border-l border-slate-200 pl-2">
          {!preloaded && lazy.isPending ? <Loading label="Loading children…" /> : null}
          {lazy.isError ? (
            <p role="alert" className="px-2 py-1 text-xs text-red-700">
              Could not load children: {lazy.error.message}{" "}
              <button type="button" className="underline" onClick={() => void lazy.refetch()}>Retry</button>
            </p>
          ) : null}
          {children && children.length === 0 ? <p className="px-2 py-1 text-xs text-slate-500">No child nodes</p> : null}
          {children && children.length > 0 ? (
            <TreeList nodes={children} selectedId={selectedId} openIds={openIds} conflicts={conflicts} onSelect={onSelect} />
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

export function TreeList({ nodes, selectedId, openIds, conflicts, onSelect }: { nodes: TreeRowNode[] } & Omit<RowProps, "node">) {
  return (
    <ul className="space-y-0.5">
      {nodes.map((n) => (
        <TreeRow key={n.id} node={n} selectedId={selectedId} openIds={openIds} conflicts={conflicts} onSelect={onSelect} />
      ))}
    </ul>
  );
}
