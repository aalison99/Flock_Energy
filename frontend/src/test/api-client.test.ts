import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { ApiError, client, toApiError, unwrap } from "../lib/api-client";
import { errorBody } from "./fixtures";
import { server } from "./server";

describe("toApiError", () => {
  it("maps the error envelope", () => {
    const e = toApiError(errorBody("not_found", "No such meter", { meter_id: "J1" }), 404);
    expect(e).toBeInstanceOf(ApiError);
    expect(e).toMatchObject({ status: 404, code: "not_found", message: "No such meter", details: { meter_id: "J1" } });
  });

  it("falls back for non-envelope bodies", () => {
    const e = toApiError("<html>Bad gateway</html>", 502);
    expect(e).toMatchObject({ status: 502, code: "http_502" });
  });
});

describe("unwrap", () => {
  it("returns data on success", async () => {
    const page = await unwrap(client.GET("/api/v1/meters", { params: { query: {} } }));
    expect(page.items).toHaveLength(1);
  });

  it("throws a typed ApiError from the envelope", async () => {
    server.use(
      http.get("*/api/v1/meters/:id", () => HttpResponse.json(errorBody("not_found", "Meter J999999 not found"), { status: 404 })),
    );
    const call = unwrap(client.GET("/api/v1/meters/{meter_id}", { params: { path: { meter_id: "J999999" } } }));
    await expect(call).rejects.toMatchObject({ name: "ApiError", status: 404, code: "not_found" });
  });

  it("maps a network failure to network_error", async () => {
    server.use(http.get("*/api/v1/health/ready", () => HttpResponse.error()));
    await expect(unwrap(client.GET("/api/v1/health/ready"))).rejects.toMatchObject({ code: "network_error", status: 0 });
  });
});
