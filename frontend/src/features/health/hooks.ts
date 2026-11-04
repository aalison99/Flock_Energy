import { useQuery } from "@tanstack/react-query";
import { getReadiness } from "./api";

export const READINESS_POLL_MS = 30_000;

export function useReadiness() {
  return useQuery({
    queryKey: ["health", "ready"],
    queryFn: getReadiness,
    refetchInterval: READINESS_POLL_MS,
  });
}
