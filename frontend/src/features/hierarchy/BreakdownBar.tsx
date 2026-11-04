import type { StatusBreakdown } from "./types";

const SEGMENTS = [
  { key: "installed", label: "installed", cls: "bg-installed" },
  { key: "faulty", label: "faulty", cls: "bg-faulty" },
  { key: "decommissioned", label: "decommissioned", cls: "bg-decommissioned" },
  { key: "unknown", label: "unknown", cls: "bg-slate-300" },
] as const;

/** Thin stacked bar of meter statuses. The text label carries the numbers for assistive tech. */
export function BreakdownBar({ breakdown }: { breakdown: StatusBreakdown }) {
  const total = SEGMENTS.reduce((n, s) => n + breakdown[s.key], 0);
  const label = SEGMENTS.map((s) => `${breakdown[s.key]} ${s.label}`).join(", ");
  return (
    <div role="img" aria-label={`Status: ${label}`} title={label} className="flex h-1.5 w-full overflow-hidden rounded bg-slate-100">
      {total > 0
        ? SEGMENTS.map((s) =>
            breakdown[s.key] > 0 ? (
              <div key={s.key} data-segment={s.key} className={s.cls} style={{ width: `${(breakdown[s.key] / total) * 100}%` }} />
            ) : null,
          )
        : null}
    </div>
  );
}
