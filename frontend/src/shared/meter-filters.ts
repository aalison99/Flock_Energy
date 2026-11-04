import { useCallback, useEffect, useMemo } from "react";
import { useSearchParams } from "react-router";
import type { components } from "../generated/schema";

type S = components["schemas"];

export const DEFAULT_SORT = "meter_id";

// Allowed values, typed against the generated schema so a spec change breaks the build here.
const STATUSES = ["installed", "faulty", "decommissioned", "unknown"] as const satisfies readonly S["InstallStatus"][];
const PHASES = ["single", "three", "unknown"] as const satisfies readonly S["PhaseType"][];
const INSTALL_TYPES = ["whole_current", "ct_operated", "unknown"] as const satisfies readonly S["InstallType"][];
const SORTS = ["meter_id", "-meter_id", "make", "status"] as const satisfies readonly S["MeterSort"][];

const only = (values: string[], allowed: readonly string[]) => values.filter((v) => allowed.includes(v));
const one = (value: string | null, allowed: readonly string[], fallback: string) =>
  value !== null && allowed.includes(value) ? value : fallback;

/** Everything the meters list, facets and map endpoints accept as filters, as held in the URL. */
export interface MeterFilters {
  q: string;
  status: string[];
  make: string[];
  phase: string;
  install_type: string;
  dt: string;
  sort: string;
}

const MULTI = ["status", "make"] as const;
const CLEARABLE = [...MULTI, "phase", "install_type", "dt"] as const;

export function readFilters(params: URLSearchParams): MeterFilters {
  return {
    q: params.get("q") ?? "",
    status: only(params.getAll("status"), STATUSES),
    make: params.getAll("make"),
    phase: one(params.get("phase"), PHASES, ""),
    install_type: one(params.get("install_type"), INSTALL_TYPES, ""),
    dt: params.get("dt") ?? "",
    sort: one(params.get("sort"), SORTS, DEFAULT_SORT),
  };
}

/** True when a chip/select filter (not search or sort) is set. */
export function hasActiveFilters(f: MeterFilters): boolean {
  return f.status.length > 0 || f.make.length > 0 || Boolean(f.phase || f.install_type || f.dt);
}

/** Query string (with leading "?", or "") carrying the filters, for links such as "View on map". */
export function filtersToSearch(f: MeterFilters): string {
  const p = new URLSearchParams();
  if (f.q) p.set("q", f.q);
  for (const k of MULTI) for (const v of f[k]) p.append(k, v);
  for (const k of ["phase", "install_type", "dt"] as const) if (f[k]) p.set(k, f[k]);
  const s = p.toString();
  return s ? `?${s}` : "";
}

/** Filters as typed API query params; arrays serialise as repeated keys. */
export function toApiQuery(f: MeterFilters) {
  return {
    q: f.q || undefined,
    status: f.status.length ? (f.status as S["InstallStatus"][]) : undefined,
    make: f.make.length ? f.make : undefined,
    phase: (f.phase || undefined) as S["PhaseType"] | undefined,
    install_type: (f.install_type || undefined) as S["InstallType"] | undefined,
    dt: f.dt || undefined,
  };
}

/**
 * URL-backed filters + page. Changing any filter resets the page to 1.
 * `setFilters`, `setPage` and `clearFilters` are referentially stable.
 */
export function useMeterFilters() {
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => readFilters(params), [params]);
  const page = Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1);

  // Normalise the URL: unknown enum values (status, phase, install_type, sort) are removed, never sent.
  useEffect(() => {
    const bad =
      params.getAll("status").some((v) => !STATUSES.includes(v as never)) ||
      (params.has("phase") && !PHASES.includes(filters.phase as never)) ||
      (params.has("install_type") && !INSTALL_TYPES.includes(filters.install_type as never)) ||
      (params.has("sort") && !SORTS.includes(params.get("sort") as never));
    if (!bad) return;
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        const f = readFilters(prev);
        for (const k of ["status", "phase", "install_type", "sort"] as const) next.delete(k);
        for (const v of f.status) next.append("status", v);
        if (f.phase) next.set("phase", f.phase);
        if (f.install_type) next.set("install_type", f.install_type);
        if (f.sort !== DEFAULT_SORT) next.set("sort", f.sort);
        return next;
      },
      { replace: true },
    );
  }, [params, filters, setParams]);

  const setFilters = useCallback(
    (patch: Partial<MeterFilters>, options?: { replace?: boolean }) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          for (const k of Object.keys(patch) as (keyof MeterFilters)[]) {
            next.delete(k);
            const v = patch[k];
            if (Array.isArray(v)) for (const item of v) next.append(k, item);
            else if (v && !(k === "sort" && v === DEFAULT_SORT)) next.set(k, v);
          }
          next.delete("page");
          return next;
        },
        { replace: options?.replace ?? false },
      );
    },
    [setParams],
  );

  const clearFilters = useCallback(() => {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      for (const k of CLEARABLE) next.delete(k);
      next.delete("page");
      return next;
    });
  }, [setParams]);

  const setPage = useCallback(
    (p: number, options?: { replace?: boolean }) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (p <= 1) next.delete("page");
          else next.set("page", String(p));
          return next;
        },
        { replace: options?.replace ?? false },
      );
    },
    [setParams],
  );

  return { filters, page, setFilters, setPage, clearFilters };
}
