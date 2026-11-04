import { useQuery } from "@tanstack/react-query";
import { getReadings } from "./api";
import type { Resolution } from "./types";

export function useReadings(meterId: string, resolution: Resolution) {
  return useQuery({
    queryKey: ["readings", meterId, resolution],
    queryFn: () => getReadings(meterId, resolution),
  });
}
