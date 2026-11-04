import { client, unwrap } from "../../lib/api-client";
import { toApiQuery } from "../../shared";
import type { MeterFilters } from "../../shared";
import type { BBoxResponse, Bounds, NearQuery, NearResponse } from "./types";

export const BBOX_LIMIT = 1000;

/** Meters inside the viewport (the API caps the count and flags `truncated`). */
export function getBBox(bounds: Bounds, filters: MeterFilters): Promise<BBoxResponse> {
  return unwrap(client.GET("/api/v1/geo/bbox", { params: { query: { ...toApiQuery(filters), ...bounds, limit: BBOX_LIMIT } } }));
}

export function getNear(near: NearQuery, filters: MeterFilters): Promise<NearResponse> {
  return unwrap(client.GET("/api/v1/geo/near", { params: { query: { ...toApiQuery(filters), ...near } } }));
}
