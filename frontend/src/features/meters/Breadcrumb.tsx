import type { MeterDetail } from "./types";

export function Breadcrumb({ hierarchy }: { hierarchy: MeterDetail["hierarchy"] }) {
  if (hierarchy.length === 0) return <p className="text-sm text-slate-500">Hierarchy unavailable</p>;
  return (
    <nav aria-label="Hierarchy" className="text-sm text-slate-600">
      <ol className="flex flex-wrap items-center gap-1">
        {hierarchy.map((node, i) => (
          <li key={`${node.level}-${i}`} className="flex items-center gap-1" title={node.level}>
            {i > 0 ? <span aria-hidden="true">›</span> : null}
            <span>{node.name ?? node.code ?? node.level}</span>
          </li>
        ))}
      </ol>
    </nav>
  );
}
