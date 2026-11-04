import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { errorBody, readiness } from "./fixtures";
import { renderApp } from "./render";
import { server } from "./server";

describe("Layout + health pill", () => {
  it("shows the nav links", async () => {
    renderApp("/meters");
    for (const name of ["Dashboard", "Meters", "Map", "Hierarchy"]) {
      expect(screen.getByRole("link", { name })).toBeInTheDocument();
    }
  });

  it("shows breaker state and meter count when ready", async () => {
    renderApp("/meters");
    expect(await screen.findByText("Portal OK")).toBeInTheDocument();
    expect(screen.getByText(/1,234 meters indexed/)).toBeInTheDocument();
  });

  it("shows an open breaker", async () => {
    server.use(http.get("*/api/v1/health/ready", () => HttpResponse.json(readiness({ portal: { breaker: "open" }, status: "not_ready" }))));
    renderApp("/meters");
    expect(await screen.findByText("Portal unavailable")).toBeInTheDocument();
  });

  it("shows a half-open breaker as recovering", async () => {
    server.use(http.get("*/api/v1/health/ready", () => HttpResponse.json(readiness({ portal: { breaker: "half_open" } }))));
    renderApp("/meters");
    expect(await screen.findByText("Portal recovering")).toBeInTheDocument();
  });

  it("says the index is syncing when it is not ready", async () => {
    server.use(
      http.get("*/api/v1/health/ready", () =>
        HttpResponse.json(readiness({ status: "not_ready", index: { ready: false, meter_count: 0, last_sync_at: null } })),
      ),
    );
    renderApp("/meters");
    expect(await screen.findByText("Index syncing…")).toBeInTheDocument();
  });

  it("exposes the pill as a status region with visible text", async () => {
    renderApp("/meters");
    const region = (await screen.findByText("Portal OK")).closest('[role="status"]') as HTMLElement;
    expect(region).toHaveTextContent("Portal OK");
    expect(region).not.toHaveAttribute("aria-label");
  });

  it("has a skip-to-content link targeting the main region", () => {
    renderApp("/meters");
    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main");
  });

  it("shows API unreachable on failure", async () => {
    server.use(http.get("*/api/v1/health/ready", () => HttpResponse.json(errorBody("internal_error", "boom"), { status: 500 })));
    renderApp("/meters");
    expect(await screen.findByText("API unreachable", {}, { timeout: 3000 })).toBeInTheDocument();
  });
});
