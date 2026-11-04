import { ApiError } from "../../lib/api-error";
import { Badge } from "../../shared";
import type { BadgeTone } from "../../shared";
import type { NearMeter } from "./types";

export interface NearForm {
  lat: string;
  lng: string;
  radius: string;
}

interface Props {
  form: NearForm;
  onFormChange: (form: NearForm) => void;
  onSubmit: () => void;
  formError: string | null;
  isLoading: boolean;
  error: Error | null;
  results: NearMeter[] | undefined;
  onSelect: (m: NearMeter) => void;
}

const input = "w-full rounded border border-slate-300 bg-white px-2 py-1 text-sm";

export function statusTone(status: string): BadgeTone {
  return status === "installed" || status === "faulty" || status === "decommissioned" ? status : "neutral";
}

/** "Find meters near a point": coordinates (typed or picked on the map), radius, and the nearest-first list. */
export function NearPanel({ form, onFormChange, onSubmit, formError, isLoading, error, results, onSelect }: Props) {
  const set = (k: keyof NearForm) => (e: React.ChangeEvent<HTMLInputElement>) => onFormChange({ ...form, [k]: e.target.value });
  const sorted = results ? [...results].sort((a, b) => a.distance_km - b.distance_km || a.meter.meter_id.localeCompare(b.meter.meter_id)) : undefined;

  return (
    <section aria-label="Find meters near a point" className="space-y-3 rounded-lg border border-slate-200 bg-white p-3">
      <h2 className="text-sm font-semibold">Find meters near a point</h2>
      <p className="text-xs text-slate-500">Click the map to pick a point, or type coordinates.</p>
      <form
        className="grid grid-cols-3 gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
      >
        <label className="text-xs text-slate-600">
          Latitude
          <input className={input} inputMode="decimal" value={form.lat} onChange={set("lat")} />
        </label>
        <label className="text-xs text-slate-600">
          Longitude
          <input className={input} inputMode="decimal" value={form.lng} onChange={set("lng")} />
        </label>
        <label className="text-xs text-slate-600">
          Radius (km)
          <input className={input} inputMode="decimal" value={form.radius} onChange={set("radius")} />
        </label>
        <button type="submit" className="col-span-3 rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700">
          Find nearby meters
        </button>
      </form>
      {formError ? (
        <p role="alert" className="text-xs text-red-700">
          {formError}
        </p>
      ) : null}

      {isLoading ? (
        <p role="status" className="text-sm text-slate-500">
          Searching…
        </p>
      ) : error ? (
        <p role="alert" className="text-sm text-red-700">
          {error instanceof ApiError && error.status === 409
            ? "The local index is still syncing, so nearby search isn't available yet."
            : error.message}
        </p>
      ) : sorted ? (
        sorted.length === 0 ? (
          <p className="text-sm text-slate-500">No meters within that radius.</p>
        ) : (
          <ul aria-label="Nearby meters" className="max-h-72 divide-y divide-slate-100 overflow-y-auto">
            {sorted.map((m) => (
              <li key={m.meter.meter_id}>
                <button
                  type="button"
                  onClick={() => onSelect(m)}
                  className="flex w-full items-center justify-between gap-2 py-1.5 text-left text-sm hover:bg-slate-50"
                >
                  <span className="font-medium text-sky-700">{m.meter.meter_id}</span>
                  <span className="text-slate-600">{m.distance_km.toFixed(3)} km</span>
                  <Badge tone={statusTone(m.meter.install_status)}>{m.meter.install_status}</Badge>
                </button>
              </li>
            ))}
          </ul>
        )
      ) : null}
    </section>
  );
}
