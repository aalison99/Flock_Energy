import { client, unwrap } from "../../lib/api-client";
import type { MeterDetail, MeterPage } from "./types";

export interface MeterListParams {
  q?: string;
  page: number;
  pageSize: number;
}

export function listMeters({ q, page, pageSize }: MeterListParams): Promise<MeterPage> {
  return unwrap(
    client.GET("/api/v1/meters", {
      params: { query: { q: q || undefined, page, page_size: pageSize } },
    }),
  );
}

export function getMeter(meterId: string): Promise<MeterDetail> {
  return unwrap(client.GET("/api/v1/meters/{meter_id}", { params: { path: { meter_id: meterId } } }));
}
