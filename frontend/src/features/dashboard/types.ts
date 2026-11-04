import type { components } from "../../generated/schema";

type S = components["schemas"];
export type Summary = S["FleetSummaryOut"];
export type AnomalyList = S["AnomalyListResponse"];
export type Anomaly = S["AnomalyOut"];
export type Severity = S["Severity"];
export type DtLoad = S["TransformerLoadResponse"];
export type DtLoadItem = S["DtLoadOut"];
export type DataQuality = S["DataQualityResponse"];
export type SyncStatus = S["SyncStatusResponse"];
export type SyncRun = S["SyncRunOut"];

export const SEVERITIES: Severity[] = ["error", "warning", "info"];

export interface AnomalyQuery {
  node: string;
  rule: string;
  severity: string;
  page: number;
}
