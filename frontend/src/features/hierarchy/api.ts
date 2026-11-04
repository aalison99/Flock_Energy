import { client, unwrap } from "../../lib/api-client";
import type { Consumption, ConsumptionResolution, NodeDetail, NodeMeters } from "./types";
import type { components } from "../../generated/schema";

export function getTree(depth = 2): Promise<components["schemas"]["TreeResponse"]> {
  return unwrap(client.GET("/api/v1/hierarchy", { params: { query: { depth } } }));
}

export function getNode(id: string): Promise<NodeDetail> {
  return unwrap(client.GET("/api/v1/hierarchy/node", { params: { query: { id } } }));
}

export function getNodeMeters(id: string, page: number, pageSize: number): Promise<NodeMeters> {
  return unwrap(client.GET("/api/v1/hierarchy/node/meters", { params: { query: { id, page, page_size: pageSize } } }));
}

export function getConsumption(node: string, resolution: ConsumptionResolution): Promise<Consumption> {
  return unwrap(client.GET("/api/v1/analytics/consumption", { params: { query: { node, resolution } } }));
}

/** Only the total matters, so ask for a one-row page. */
export async function getAnomalyTotal(node: string): Promise<number> {
  const page = await unwrap(client.GET("/api/v1/analytics/anomalies", { params: { query: { node, page_size: 1 } } }));
  return page.total;
}

/** Ids of every node with a name conflict, paging until the API says there are no more. */
export async function getNameConflictIds(): Promise<string[]> {
  const ids: string[] = [];
  for (let page = 1; ; page++) {
    const res = await unwrap(
      client.GET("/api/v1/data-quality", { params: { query: { check: "name_conflict", page, page_size: 200 } } }),
    );
    ids.push(...res.items.map((i) => i.entity_id));
    if (!res.has_next) return ids;
  }
}
