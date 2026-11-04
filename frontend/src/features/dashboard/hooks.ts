import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getAnomalies, getDataQuality, getDtLoad, getSummary, getSyncStatus, startSync } from "./api";
import type { AnomalyQuery } from "./types";

export const SYNC_POLL_MS = 5_000;

export function useSummary() {
  return useQuery({ queryKey: ["dashboard", "summary"], queryFn: getSummary });
}

export function useAnomalies(q: AnomalyQuery) {
  return useQuery({ queryKey: ["dashboard", "anomalies", q], queryFn: () => getAnomalies(q), placeholderData: keepPreviousData });
}

export function useDtLoad() {
  return useQuery({ queryKey: ["dashboard", "dt-load"], queryFn: getDtLoad });
}

export function useQualitySummary() {
  return useQuery({ queryKey: ["dashboard", "quality"], queryFn: () => getDataQuality() });
}

export function useQualityIssues(check: string, enabled: boolean) {
  return useQuery({ queryKey: ["dashboard", "quality", check], queryFn: () => getDataQuality(check), enabled });
}

/** Polls every 5 s while the latest run is still running. */
export function useSyncStatus() {
  return useQuery({
    queryKey: ["sync", "status"],
    queryFn: getSyncStatus,
    refetchInterval: (query) => (query.state.data?.latest?.status === "running" ? SYNC_POLL_MS : false),
  });
}

export function useStartSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: startSync,
    // Success starts polling; a 409 means one is already running, so pick it up too.
    onSettled: () => qc.invalidateQueries({ queryKey: ["sync", "status"] }),
  });
}

/** Called when a sync finishes so every dashboard panel shows the new data. */
export function useRefreshDashboard() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["dashboard"] });
}
