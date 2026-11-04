import { keepPreviousData, useQuery } from "@tanstack/react-query";
import type { MeterFilters } from "../../shared";
import { getBBox, getNear } from "./api";
import type { Bounds, NearQuery } from "./types";

// Sort and page do not affect geo results, so they stay out of the cache key.
const geoFilters = (f: MeterFilters): MeterFilters => ({ ...f, sort: "" });

export function useBBox(bounds: Bounds | null, filters: MeterFilters) {
  return useQuery({
    queryKey: ["geo", "bbox", bounds, geoFilters(filters)],
    queryFn: () => getBBox(bounds as Bounds, filters),
    enabled: bounds !== null,
    placeholderData: keepPreviousData,
  });
}

export function useNear(near: NearQuery | null, filters: MeterFilters) {
  return useQuery({
    queryKey: ["geo", "near", near, geoFilters(filters)],
    queryFn: () => getNear(near as NearQuery, filters),
    enabled: near !== null,
  });
}
