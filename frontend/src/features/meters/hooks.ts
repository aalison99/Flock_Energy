import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { getMeter, listMeters } from "./api";
import type { MeterListParams } from "./api";

export function useMeters(params: MeterListParams) {
  return useQuery({
    queryKey: ["meters", "list", params],
    queryFn: () => listMeters(params),
    placeholderData: keepPreviousData,
  });
}

export function useMeter(meterId: string) {
  return useQuery({
    queryKey: ["meters", "detail", meterId],
    queryFn: () => getMeter(meterId),
  });
}
