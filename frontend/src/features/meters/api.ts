import type { components } from "../../generated/schema";
import { client, unwrap } from "../../lib/api-client";
import { toApiQuery } from "../../shared";
import type { MeterFilters } from "../../shared";
import type { FacetsResponse, MeterAnomalies, MeterDetail, MeterPage } from "./types";

export interface MeterListParams {
  filters: MeterFilters;
  page: number;
  pageSize: number;
}

export function listMeters({ filters, page, pageSize }: MeterListParams): Promise<MeterPage> {
  return unwrap(
    client.GET("/api/v1/meters", {
      params: {
        query: { ...toApiQuery(filters), sort: filters.sort as components["schemas"]["MeterSort"], page, page_size: pageSize },
      },
    }),
  );
}

/** Counts per value for each facet field; each field's counts exclude its own filter (server side). */
export function getFacets(filters: MeterFilters): Promise<FacetsResponse> {
  return unwrap(client.GET("/api/v1/meters/facets", { params: { query: toApiQuery(filters) } }));
}

export function getMeter(meterId: string): Promise<MeterDetail> {
  return unwrap(client.GET("/api/v1/meters/{meter_id}", { params: { path: { meter_id: meterId } } }));
}

export function getMeterAnomalies(meterId: string): Promise<MeterAnomalies> {
  return unwrap(client.GET("/api/v1/meters/{meter_id}/anomalies", { params: { path: { meter_id: meterId } } }));
}
