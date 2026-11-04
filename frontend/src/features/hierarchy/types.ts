import type { components } from "../../generated/schema";

type S = components["schemas"];
export type StatusBreakdown = S["StatusBreakdown"];
export type NodeDetail = S["NodeDetailOut"];
export type NodeMeters = S["Page_MeterSummary_"];
export type Consumption = S["ConsumptionResponse"];
export type ConsumptionResolution = Consumption["resolution"];
export type MeterRow = S["MeterSummary"];

/** What the tree needs from a node. Full tree nodes carry a breakdown; lazily fetched children do not. */
export interface TreeRowNode {
  id: string;
  level: S["HierarchyLevel"];
  code: string;
  name: string;
  meter_count: number;
  status_breakdown?: StatusBreakdown;
  unplaced_count?: number;
  children?: TreeRowNode[];
}
