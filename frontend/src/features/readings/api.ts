import { client, unwrap } from "../../lib/api-client";
import type { ReadingSeries, Resolution } from "./types";

export function getReadings(meterId: string, resolution: Resolution): Promise<ReadingSeries> {
  return unwrap(
    client.GET("/api/v1/meters/{meter_id}/readings", {
      params: { path: { meter_id: meterId }, query: { resolution } },
    }),
  );
}
