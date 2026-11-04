import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import {
  anomalyList,
  bboxResponse,
  consumption,
  dtLoad,
  facets,
  meterDetail,
  meterPage,
  meterSummary,
  nodeDetail,
  quality,
  readiness,
  readingSeries,
  summary,
  syncStatus,
  treeResponse,
} from "./fixtures";

export const handlers = [
  http.get("*/api/v1/health/ready", () => HttpResponse.json(readiness())),
  http.get("*/api/v1/meters/facets", () => HttpResponse.json(facets())),
  http.get("*/api/v1/geo/bbox", () => HttpResponse.json(bboxResponse([]))),
  http.get("*/api/v1/geo/near", () => HttpResponse.json({ items: [] })),
  http.get("*/api/v1/meters", () => HttpResponse.json(meterPage([meterSummary()]))),
  http.get("*/api/v1/meters/:id", ({ params }) =>
    HttpResponse.json(meterDetail({ meter_id: String(params.id) })),
  ),
  http.get("*/api/v1/meters/:id/anomalies", ({ params }) =>
    HttpResponse.json({ meter_id: String(params.id), items: [] }),
  ),
  http.get("*/api/v1/hierarchy/node/meters", () => HttpResponse.json(meterPage([meterSummary()]))),
  http.get("*/api/v1/hierarchy/node", () => HttpResponse.json(nodeDetail())),
  http.get("*/api/v1/hierarchy", () => HttpResponse.json(treeResponse())),
  http.get("*/api/v1/data-quality", () => HttpResponse.json(quality())),
  http.get("*/api/v1/analytics/summary", () => HttpResponse.json(summary())),
  http.get("*/api/v1/analytics/consumption", () => HttpResponse.json(consumption())),
  http.get("*/api/v1/analytics/anomalies", () => HttpResponse.json(anomalyList([]))),
  http.get("*/api/v1/analytics/transformers/load", () => HttpResponse.json(dtLoad([]))),
  http.get("*/api/v1/sync/status", () => HttpResponse.json(syncStatus())),
  http.get("*/api/v1/meters/:id/readings", () => HttpResponse.json(readingSeries())),
];

export const server = setupServer(...handlers);
