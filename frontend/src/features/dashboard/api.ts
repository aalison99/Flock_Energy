import { client, unwrap } from "../../lib/api-client";
import type { AnomalyList, AnomalyQuery, DataQuality, DtLoad, Severity, Summary, SyncRun, SyncStatus } from "./types";

export const ANOMALY_PAGE_SIZE = 10;
export const ISSUES_PAGE_SIZE = 50;

export function getSummary(): Promise<Summary> {
  return unwrap(client.GET("/api/v1/analytics/summary"));
}

export function getAnomalies(q: AnomalyQuery): Promise<AnomalyList> {
  return unwrap(
    client.GET("/api/v1/analytics/anomalies", {
      params: {
        query: {
          node: q.node || undefined,
          rule: q.rule || undefined,
          severity: (q.severity || undefined) as Severity | undefined,
          page: q.page,
          page_size: ANOMALY_PAGE_SIZE,
        },
      },
    }),
  );
}

export function getDtLoad(): Promise<DtLoad> {
  return unwrap(client.GET("/api/v1/analytics/transformers/load", { params: { query: { sort: "utilisation", limit: 10 } } }));
}

/** Without `check` this is the summary (counts per check) plus the first page of all issues. */
export function getDataQuality(check?: string): Promise<DataQuality> {
  return unwrap(
    client.GET("/api/v1/data-quality", { params: { query: { check, page_size: check ? ISSUES_PAGE_SIZE : 1 } } }),
  );
}

export function getSyncStatus(): Promise<SyncStatus> {
  return unwrap(client.GET("/api/v1/sync/status"));
}

export function startSync(): Promise<SyncRun> {
  return unwrap(client.POST("/api/v1/sync", { body: { include_readings: true } }));
}
