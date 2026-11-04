import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { meterDetail, meterPage, meterSummary, readiness, readingSeries } from "./fixtures";

export const handlers = [
  http.get("*/api/v1/health/ready", () => HttpResponse.json(readiness())),
  http.get("*/api/v1/meters", () => HttpResponse.json(meterPage([meterSummary()]))),
  http.get("*/api/v1/meters/:id", ({ params }) =>
    HttpResponse.json(meterDetail({ meter_id: String(params.id) })),
  ),
  http.get("*/api/v1/meters/:id/readings", () => HttpResponse.json(readingSeries())),
];

export const server = setupServer(...handlers);
