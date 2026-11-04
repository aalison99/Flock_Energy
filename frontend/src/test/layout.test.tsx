import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { errorBody, readiness } from "./fixtures";
import { renderApp } from "./render";
import { server } from "./server";

describe("Layout + health pill", () => {
  it("shows the nav links", async () => {
    renderApp("/");
    for (const name of ["Dashboard", "Meters", "Map", "Hierarchy"]) {
      expect(screen.getByRole("link", { name })).toBeInTheDocument();
    }
  });

  it("shows breaker state and meter count when ready", async () => {
    renderApp("/");
    expect(await screen.findByText("Portal: closed")).toBeInTheDocument();
    expect(screen.getByText(/1,234 meters indexed/)).toBeInTheDocument();
  });

  it("shows an open breaker", async () => {
    server.use(http.get("*/api/v1/health/ready", () => HttpResponse.json(readiness({ portal: { breaker: "open" }, status: "not_ready" }))));
    renderApp("/");
    expect(await screen.findByText("Portal: open")).toBeInTheDocument();
  });

  it("shows API unreachable on failure", async () => {
    server.use(http.get("*/api/v1/health/ready", () => HttpResponse.json(errorBody("internal_error", "boom"), { status: 500 })));
    renderApp("/");
    expect(await screen.findByText("API unreachable", {}, { timeout: 3000 })).toBeInTheDocument();
  });
});
