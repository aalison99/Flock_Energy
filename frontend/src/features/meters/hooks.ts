import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { getFacets, getMeter, listMeters } from "./api";
import type { MeterListParams } from "./api";
import type { MeterFilters } from "../../shared";

export function useMeters(params: MeterListParams) {
  return useQuery({
    queryKey: ["meters", "list", params],
    queryFn: () => listMeters(params),
    placeholderData: keepPreviousData,
  });
}

export function useFacets(filters: MeterFilters) {
  // Facet counts do not depend on sort, so the key blanks it and changing sort does not refetch them.
  return useQuery({
    queryKey: ["meters", "facets", { ...filters, sort: "" }],
    queryFn: () => getFacets(filters),
    placeholderData: keepPreviousData,
  });
}

export function useMeter(meterId: string) {
  return useQuery({
    queryKey: ["meters", "detail", meterId],
    queryFn: () => getMeter(meterId),
  });
}
