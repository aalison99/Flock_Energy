import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { getAnomalyTotal, getConsumption, getNameConflictIds, getNode, getNodeMeters, getTree } from "./api";
import type { ConsumptionResolution } from "./types";

export const NODE_METERS_PAGE_SIZE = 10;

export function useTree() {
  return useQuery({ queryKey: ["hierarchy", "tree"], queryFn: () => getTree(2) });
}

export function useNode(id: string, enabled = true) {
  return useQuery({ queryKey: ["hierarchy", "node", id], queryFn: () => getNode(id), enabled });
}

export function useNodeMeters(id: string, page: number) {
  return useQuery({
    queryKey: ["hierarchy", "meters", id, page],
    queryFn: () => getNodeMeters(id, page, NODE_METERS_PAGE_SIZE),
    placeholderData: keepPreviousData,
  });
}

export function useConsumption(node: string, resolution: ConsumptionResolution) {
  return useQuery({ queryKey: ["hierarchy", "consumption", node, resolution], queryFn: () => getConsumption(node, resolution) });
}

export function useNodeAnomalyTotal(node: string) {
  return useQuery({ queryKey: ["hierarchy", "anomaly-total", node], queryFn: () => getAnomalyTotal(node) });
}

/** Fetched once; a failure just means no warning badges. */
export function useNameConflicts() {
  return useQuery({
    queryKey: ["hierarchy", "name-conflicts"],
    queryFn: async () => new Set(await getNameConflictIds()),
    staleTime: Infinity,
  });
}
