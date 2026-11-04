import { RESOLUTIONS } from "./types";
import type { Resolution } from "./types";

export function ResolutionToggle({ value, onChange }: { value: Resolution; onChange: (r: Resolution) => void }) {
  return (
    <div role="group" aria-label="Resolution" className="inline-flex overflow-hidden rounded border border-slate-300">
      {RESOLUTIONS.map((r) => (
        <button
          key={r}
          type="button"
          aria-pressed={value === r}
          onClick={() => onChange(r)}
          className={`px-3 py-1 text-sm capitalize ${
            value === r ? "bg-slate-900 text-white" : "bg-white text-slate-700 hover:bg-slate-100"
          }`}
        >
          {r}
        </button>
      ))}
    </div>
  );
}
