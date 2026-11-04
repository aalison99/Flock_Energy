import { hasActiveFilters } from "../../shared";
import type { MeterFilters } from "../../shared";
import { useFacets } from "./hooks";

export const SORT_OPTIONS = [
  { value: "meter_id", label: "Meter ID (A to Z)" },
  { value: "-meter_id", label: "Meter ID (Z to A)" },
  { value: "make", label: "Make" },
  { value: "status", label: "Status" },
];

interface Props {
  filters: MeterFilters;
  onChange: (patch: Partial<MeterFilters>) => void;
  onClear: () => void;
}

const selectCls = "rounded border border-slate-300 bg-white px-2 py-1 text-sm";

function Chip({ label, count, selected, onClick }: { label: string; count: number; selected: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-xs font-medium ${
        selected ? "border-slate-900 bg-slate-900 text-white" : "border-slate-300 bg-white text-slate-700 hover:bg-slate-100"
      }`}
    >
      {label} ({count})
    </button>
  );
}

function toggle(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

/** Values to show for a facet: non-zero counts, plus any selected value (even at zero). */
function visibleValues(counts: Record<string, number>, selected: string[]): [string, number][] {
  const entries = Object.entries(counts).filter(([v, n]) => n > 0 || selected.includes(v));
  for (const v of selected) if (!(v in counts)) entries.push([v, 0]);
  return entries.sort(([a], [b]) => a.localeCompare(b));
}

/** Status / make / phase / install type chips with counts, the DT select, sort and Clear filters. */
export function FilterBar({ filters, onChange, onClear }: Props) {
  const { data, isPending, isError, error, refetch } = useFacets(filters);
  const facets = data?.facets ?? {};
  const active = hasActiveFilters(filters);

  const groups: { key: "status" | "make" | "phase" | "install_type"; label: string; multi: boolean }[] = [
    { key: "status", label: "Status", multi: true },
    { key: "make", label: "Make", multi: true },
    { key: "phase", label: "Phase", multi: false },
    { key: "install_type", label: "Install type", multi: false },
  ];

  const dtCounts = facets.dt ?? {};
  const dtOptions = visibleValues(dtCounts, filters.dt ? [filters.dt] : []).sort(([a], [b]) => a.localeCompare(b));

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-3" aria-label="Filters" role="group">
      {isPending ? (
        <p className="text-sm text-slate-500">Loading filters…</p>
      ) : isError ? (
        <div role="alert" className="flex flex-wrap items-center gap-2 text-sm text-red-800">
          <span>Could not load filter counts.</span>
          <span>{error.message}</span>
          <button type="button" onClick={() => void refetch()} className="rounded border border-red-300 bg-white px-3 py-1 hover:bg-red-50">
            Retry filters
          </button>
        </div>
      ) : null}
      {groups.map(({ key, label, multi }) => {
        const selected = multi ? (filters[key] as string[]) : filters[key] ? [filters[key] as string] : [];
        const values = visibleValues(facets[key] ?? {}, selected);
        if (values.length === 0) return null;
        return (
          <div key={key} role="group" aria-label={label} className="flex flex-wrap items-center gap-2">
            <span className="w-24 text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</span>
            {values.map(([value, count]) => (
              <Chip
                key={value}
                label={value}
                count={count}
                selected={selected.includes(value)}
                onClick={() =>
                  onChange(
                    multi
                      ? { [key]: toggle(selected, value) }
                      : { [key]: selected.includes(value) ? "" : value },
                  )
                }
              />
            ))}
          </div>
        );
      })}
      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm text-slate-600">
          DT
          <select className={selectCls} value={filters.dt} onChange={(e) => onChange({ dt: e.target.value })}>
            <option value="">All</option>
            {dtOptions.map(([code, count]) => (
              <option key={code} value={code}>
                {code} ({count})
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          Sort
          <select className={selectCls} value={filters.sort} onChange={(e) => onChange({ sort: e.target.value })}>
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        {active ? (
          <button type="button" onClick={onClear} className="rounded border border-slate-300 bg-white px-3 py-1 text-sm hover:bg-slate-100">
            Clear filters
          </button>
        ) : null}
      </div>
    </div>
  );
}
