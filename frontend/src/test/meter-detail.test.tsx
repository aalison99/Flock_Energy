import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeAll, describe, expect, it } from "vitest";
import { errorBody, meterDetail, readingSeries } from "./fixtures";
import { currentSearch, renderApp } from "./render";
import { server } from "./server";

// Warm the lazy chart/map chunks so tests are not racing a cold module load.
beforeAll(async () => {
  await Promise.all([import("../features/readings/ReadingsChart"), import("../features/meters/MiniMap")]);
}, 30_000);

describe("Meter detail", () => {
  it("shows loading, then nameplate, breadcrumb, freshness and summary", async () => {
    renderApp("/meters/J100000");
    expect(screen.getByText("Loading meter…")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "J100000" })).toBeInTheDocument();
    expect(screen.getByText("SE33962")).toBeInTheDocument();
    const crumbs = screen.getByRole("navigation", { name: "Hierarchy" });
    expect(crumbs).toHaveTextContent("Jaipur Zone 1");
    expect(crumbs).toHaveTextContent("Malviya Nagar DT 1");
    expect(screen.getByText(/Source: portal/)).toBeInTheDocument();
    expect(screen.queryByText("stale")).not.toBeInTheDocument();
    expect(await screen.findByText("12.5")).toBeInTheDocument();
    expect(screen.getByText("Total kWh")).toBeInTheDocument();
    expect(screen.getByText("half hourly (30 min)")).toBeInTheDocument();
  });

  it("shows the stale badge", async () => {
    server.use(
      http.get("*/api/v1/meters/:id", () =>
        HttpResponse.json(meterDetail({ meta: { source: "portal", fetched_at: "2026-11-04T12:00:00Z", stale: true } })),
      ),
    );
    renderApp("/meters/J100000");
    expect(await screen.findByText("stale")).toBeInTheDocument();
  });

  it("shows a not-found state with a link back on 404", async () => {
    server.use(
      http.get("*/api/v1/meters/:id", () => HttpResponse.json(errorBody("not_found", "Meter not found"), { status: 404 })),
    );
    renderApp("/meters/J999999");
    expect(await screen.findByText("Meter not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to meters" })).toHaveAttribute("href", "/meters");
  });

  it("resolution toggle changes the request and the URL", async () => {
    const seen: (string | null)[] = [];
    server.use(
      http.get("*/api/v1/meters/:id/readings", ({ request }) => {
        const res = new URL(request.url).searchParams.get("resolution");
        seen.push(res);
        return HttpResponse.json(readingSeries());
      }),
    );
    const { router } = renderApp("/meters/J100000");
    await screen.findByText("Total kWh");
    expect(seen[0]).toBe("daily");
    await userEvent.click(screen.getByRole("button", { name: "hourly" }));
    await waitFor(() => expect(currentSearch(router)).toBe("?res=hourly"));
    await waitFor(() => expect(seen).toContain("hourly"));
    expect(screen.getByRole("button", { name: "hourly" })).toHaveAttribute("aria-pressed", "true");
  });

  it("restores the resolution from the URL", async () => {
    const seen: (string | null)[] = [];
    server.use(
      http.get("*/api/v1/meters/:id/readings", ({ request }) => {
        seen.push(new URL(request.url).searchParams.get("resolution"));
        return HttpResponse.json(readingSeries());
      }),
    );
    renderApp("/meters/J100000?res=raw");
    await screen.findByText("Total kWh");
    expect(seen[0]).toBe("raw");
  });

  it("shows the 422 message inline and offers daily", async () => {
    server.use(
      http.get("*/api/v1/meters/:id/readings", ({ request }) => {
        const res = new URL(request.url).searchParams.get("resolution");
        return res === "daily"
          ? HttpResponse.json(readingSeries())
          : HttpResponse.json(errorBody("validation_error", "Resolution too fine for this range; use daily."), { status: 422 });
      }),
    );
    const { router } = renderApp("/meters/J100000?res=raw");
    expect(await screen.findByText("Resolution too fine for this range; use daily.")).toBeInTheDocument();
    // The meter header is still shown.
    expect(screen.getByRole("heading", { name: "J100000" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show daily" }));
    await waitFor(() => expect(currentSearch(router)).toBe(""));
    expect(await screen.findByText("Total kWh")).toBeInTheDocument();
  });

  it("renders the mini map when the meter has a position", async () => {
    server.use(
      http.get("*/api/v1/meters/:id", () => HttpResponse.json(meterDetail({ geo: { lat: 26.9, lng: 75.8 } }))),
    );
    const { container } = renderApp("/meters/J100000");
    await waitFor(() => expect(container.querySelector(".leaflet-container")).not.toBeNull());
  });
});
