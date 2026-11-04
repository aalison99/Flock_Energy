import "leaflet/dist/leaflet.css";
import type { Map as LeafletMap } from "leaflet";
import { useCallback, useEffect, useRef, useState } from "react";
import { Circle, CircleMarker, MapContainer, Popup, TileLayer, useMap, useMapEvents } from "react-leaflet";
import { Link } from "react-router";
import { ApiError } from "../../lib/api-error";
import { Badge, ErrorState, hasActiveFilters, useMeterFilters } from "../../shared";
import { useBBox, useNear } from "./hooks";
import { NearPanel, statusTone } from "./NearPanel";
import type { NearForm } from "./NearPanel";
import type { Bounds, NearMeter, NearQuery } from "./types";

export const JAIPUR: [number, number] = [26.9124, 75.7873];
export const JAIPUR_ZOOM = 12;
export const MOVE_DEBOUNCE_MS = 300;
export const LIST_MAX = 50;
export const RADIUS_MIN_KM = 0.1;
export const RADIUS_MAX_KM = 50;

const STATUS_COLOUR: Record<string, string> = {
  installed: "#15803d",
  faulty: "#d97706",
  decommissioned: "#64748b",
  unknown: "#94a3b8",
};

const round5 = (n: number) => Math.round(n * 1e5) / 1e5;

interface EventsProps {
  onBounds: (b: Bounds) => void;
  onPick: (lat: number, lng: number) => void;
  onMap: (m: LeafletMap) => void;
}

/** Bridges Leaflet's map events and instance to React state: debounced viewport bounds, clicks, the map handle. */
function MapEvents({ onBounds, onPick, onMap }: EventsProps) {
  const map = useMap();
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const report = useCallback(() => {
    const b = map.getBounds();
    onBounds({
      min_lat: round5(b.getSouth()),
      min_lng: round5(b.getWest()),
      max_lat: round5(b.getNorth()),
      max_lng: round5(b.getEast()),
    });
  }, [map, onBounds]);

  useEffect(() => {
    onMap(map);
    report();
    return () => clearTimeout(timer.current);
  }, [map, onMap, report]);

  useMapEvents({
    moveend: () => {
      clearTimeout(timer.current);
      timer.current = setTimeout(report, MOVE_DEBOUNCE_MS);
    },
    click: (e) => onPick(e.latlng.lat, e.latlng.lng),
  });
  return null;
}

const notice = "rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-800";

export default function MeterMapView() {
  const { filters, clearFilters } = useMeterFilters();
  const [bounds, setBounds] = useState<Bounds | null>(null);
  const [map, setMap] = useState<LeafletMap | null>(null);
  const [form, setForm] = useState<NearForm>({ lat: "", lng: "", radius: "1" });
  const [formError, setFormError] = useState<string | null>(null);
  const [near, setNear] = useState<NearQuery | null>(null);

  const bbox = useBBox(bounds, filters);
  const nearQ = useNear(near, filters);

  const run = useCallback((f: NearForm) => {
    const lat = Number(f.lat);
    const lng = Number(f.lng);
    const radius = Number(f.radius);
    if (f.lat.trim() === "" || f.lng.trim() === "" || !Number.isFinite(lat) || !Number.isFinite(lng) || lat < -90 || lat > 90 || lng < -180 || lng > 180) {
      setFormError("Enter a latitude between -90 and 90 and a longitude between -180 and 180.");
      return;
    }
    if (f.radius.trim() === "" || !Number.isFinite(radius) || radius < RADIUS_MIN_KM || radius > RADIUS_MAX_KM) {
      setFormError(`Radius must be between ${RADIUS_MIN_KM} and ${RADIUS_MAX_KM} km.`);
      return;
    }
    setFormError(null);
    setNear({ lat, lng, radius_km: radius });
  }, []);

  const onPick = useCallback(
    (lat: number, lng: number) => {
      const next = { ...form, lat: lat.toFixed(5), lng: lng.toFixed(5) };
      setForm(next);
      run(next);
    },
    [form, run],
  );

  const onSelect = (m: NearMeter) => map?.panTo([m.lat, m.lng]);

  const syncing = bbox.error instanceof ApiError && bbox.error.status === 409;
  const items = bbox.data?.items ?? [];

  return (
    <section className="space-y-3">
      <h1 className="text-xl font-semibold">Meter map</h1>
      {hasActiveFilters(filters) || filters.q ? (
        <p className="text-sm text-slate-600">
          Filters from the explorer are applied.{" "}
          <Link className="text-sky-700 hover:underline" to="/map">
            Clear filters
          </Link>
        </p>
      ) : null}

      {syncing ? (
        <div role="status" className={notice}>
          The local index is still syncing, so the map isn't available yet.
          <p className="mt-1 text-sky-700">{(bbox.error as Error).message}</p>
          <button type="button" onClick={() => void bbox.refetch()} className="mt-2 rounded border border-sky-300 bg-white px-3 py-1 hover:bg-sky-100">
            Retry
          </button>
          {hasActiveFilters(filters) || filters.q ? (
            <button type="button" onClick={clearFilters} className="ml-2 mt-2 rounded border border-sky-300 bg-white px-3 py-1 hover:bg-sky-100">
              Clear filters
            </button>
          ) : null}
        </div>
      ) : bbox.isError ? (
        <ErrorState title="Could not load meters for this view" message={bbox.error.message} />
      ) : (
        <div aria-live="polite" className="text-sm text-slate-600">
          {bbox.isPending ? (
            <p role="status">Loading meters…</p>
          ) : (
            <>
              {bbox.data?.truncated ? (
                <p role="status" className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-amber-800">
                  Showing first {items.length.toLocaleString("en-IN")}, zoom in to see all meters.
                </p>
              ) : items.length === 0 ? (
                <p>No meters in this view.</p>
              ) : (
                <p>
                  {items.length.toLocaleString("en-IN")} {items.length === 1 ? "meter" : "meters"} in view
                </p>
              )}
            </>
          )}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
        <MapContainer center={JAIPUR} zoom={JAIPUR_ZOOM} className="h-[65vh] min-h-96 w-full rounded-lg border border-slate-200">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <MapEvents onBounds={setBounds} onPick={onPick} onMap={setMap} />
          {items.map((m) => {
            const colour = STATUS_COLOUR[m.install_status] ?? STATUS_COLOUR.unknown;
            return (
              <CircleMarker
                key={m.meter_id}
                center={[m.lat, m.lng]}
                radius={6}
                pathOptions={{ color: colour, fillColor: colour, fillOpacity: 0.8, weight: 1 }}
              >
                <Popup>
                  <div className="space-y-1 text-sm">
                    <Link className="font-medium text-sky-700 hover:underline" to={`/meters/${m.meter_id}`}>
                      {m.meter_id}
                    </Link>
                    <div>
                      <Badge tone={statusTone(m.install_status)}>{m.install_status}</Badge>
                    </div>
                    <div>DT: {m.dt_code ?? "none"}</div>
                  </div>
                </Popup>
              </CircleMarker>
            );
          })}
          {near ? (
            <>
              <Circle center={[near.lat, near.lng]} radius={near.radius_km * 1000} pathOptions={{ color: "#0369a1", weight: 2, fillOpacity: 0.06 }} />
              <CircleMarker center={[near.lat, near.lng]} radius={4} pathOptions={{ color: "#0369a1", fillColor: "#0369a1", fillOpacity: 1 }} />
            </>
          ) : null}
        </MapContainer>

        <NearPanel
          form={form}
          onFormChange={setForm}
          onSubmit={() => run(form)}
          formError={formError}
          isLoading={near !== null && nearQ.isPending}
          error={near !== null && nearQ.isError ? nearQ.error : null}
          results={near !== null ? nearQ.data?.items : undefined}
          onSelect={onSelect}
        />
      </div>

      {items.length > 0 ? (
        <section aria-label="Meters in view" className="rounded-lg border border-slate-200 bg-white p-3">
          <h2 className="text-sm font-semibold">Meters in view</h2>
          <p className="text-xs text-slate-500">A list equivalent of the map markers.</p>
          <ul aria-label="Meters in view" className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3 lg:grid-cols-4">
            {items.slice(0, LIST_MAX).map((m) => (
              <li key={m.meter_id} className="flex items-center justify-between gap-2">
                <Link className="text-sky-700 hover:underline" to={`/meters/${m.meter_id}`}>
                  {m.meter_id}
                </Link>
                <Badge tone={statusTone(m.install_status)}>{m.install_status}</Badge>
              </li>
            ))}
            {items.length > LIST_MAX ? <li className="text-slate-500">+{items.length - LIST_MAX} more</li> : null}
          </ul>
        </section>
      ) : null}
    </section>
  );
}
