import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { bboxMeter, bboxResponse, errorBody, nearMeter } from "./fixtures";
import { renderApp } from "./render";
import { server } from "./server";

// jsdom has no layout or tiles, so react-leaflet is replaced by a deterministic stand-in:
// a fake map with fixed bounds, and handlers that tests fire by hand.
const fake = vi.hoisted(() => {
  type Handlers = Record<string, (e?: unknown) => void>;
  const handlers: Handlers = {};
  return {
    handlers,
    panTo: vi.fn(),
    fire: (name: string, e?: unknown) => handlers[name]?.(e),
    box: { s: 26.8, w: 75.7, n: 27.0, e: 75.9 },
    map: {
      getBounds: () => ({ getSouth: () => fake.box.s, getWest: () => fake.box.w, getNorth: () => fake.box.n, getEast: () => fake.box.e }),
      panTo: (...a: unknown[]) => fake.panTo(...a),
    },
  };
});

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children, center, zoom }: { children: ReactNode; center: number[]; zoom: number }) => (
    <div data-testid="map" data-center={center.join(",")} data-zoom={zoom}>
      {children}
    </div>
  ),
  TileLayer: () => null,
  Popup: ({ children }: { children: ReactNode }) => <div data-testid="popup">{children}</div>,
  CircleMarker: ({ children, pathOptions }: { children?: ReactNode; pathOptions?: { color?: string } }) => (
    <div data-testid="marker" data-colour={pathOptions?.color}>
      {children}
    </div>
  ),
  Circle: ({ radius }: { radius: number }) => <div data-testid="radius-circle" data-radius={radius} />,
  useMap: () => fake.map,
  useMapEvents: (h: Record<string, (e?: unknown) => void>) => {
    Object.assign(fake.handlers, h);
    return fake.map;
  },
}));

const bboxCalls: URLSearchParams[] = [];
const nearCalls: URLSearchParams[] = [];

// Warm the lazy chunk so the first test is not racing a cold module load.
beforeAll(async () => {
  await import("../features/map/MeterMapView");
}, 30_000);

beforeEach(() => {
  fake.box = { s: 26.8, w: 75.7, n: 27.0, e: 75.9 };
  fake.panTo.mockClear();
  bboxCalls.length = 0;
  nearCalls.length = 0;
});

function useBBoxHandler(items = [bboxMeter()], truncated = false) {
  server.use(
    http.get("*/api/v1/geo/bbox", ({ request }) => {
      bboxCalls.push(new URL(request.url).searchParams);
      return HttpResponse.json(bboxResponse(items, truncated));
    }),
  );
}

describe("Meter map", () => {
  it("lazy-loads, starts at Jaipur and requests the bbox with URL filters (repeated keys)", async () => {
    useBBoxHandler();
    renderApp("/map?status=faulty&status=installed&dt=DT-001");
    expect(await screen.findByTestId("map")).toHaveAttribute("data-center", "26.9124,75.7873");
    expect(screen.getByTestId("map")).toHaveAttribute("data-zoom", "12");
    await waitFor(() => expect(bboxCalls).toHaveLength(1));
    const q = bboxCalls[0]!;
    expect(q.get("min_lat")).toBe("26.8");
    expect(q.get("max_lng")).toBe("75.9");
    expect(q.getAll("status")).toEqual(["faulty", "installed"]);
    expect(q.get("dt")).toBe("DT-001");
    expect(await screen.findByText("1 meter in view")).toBeInTheDocument();
  });

  it("colours markers by status and popups link to the meter", async () => {
    useBBoxHandler([
      bboxMeter({ meter_id: "J1", install_status: "installed" }),
      bboxMeter({ meter_id: "J2", install_status: "faulty", dt_code: null }),
      bboxMeter({ meter_id: "J3", install_status: "decommissioned" }),
    ]);
    renderApp("/map");
    const markers = await screen.findAllByTestId("marker");
    expect(markers.map((m) => m.getAttribute("data-colour"))).toEqual(["#15803d", "#d97706", "#64748b"]);
    const popup = within(screen.getAllByTestId("popup")[0]!);
    expect(popup.getByRole("link", { name: "J1" })).toHaveAttribute("href", "/meters/J1");
    expect(popup.getByText("installed")).toBeInTheDocument();
    expect(popup.getByText("DT: DT-001")).toBeInTheDocument();
  });

  it("refetches the bbox after a debounced moveend", async () => {
    useBBoxHandler();
    renderApp("/map");
    await waitFor(() => expect(bboxCalls).toHaveLength(1));
    fake.box = { s: 26.5, w: 75.5, n: 26.6, e: 75.6 };
    act(() => {
      fake.fire("moveend");
      fake.fire("moveend");
    });
    await waitFor(() => expect(bboxCalls).toHaveLength(2));
    expect(bboxCalls[1]!.get("min_lat")).toBe("26.5");
    await new Promise((r) => setTimeout(r, 400));
    expect(bboxCalls).toHaveLength(2);
  });

  it("shows the truncated banner", async () => {
    useBBoxHandler([bboxMeter()], true);
    renderApp("/map");
    expect(await screen.findByText(/Showing first 1, zoom in/)).toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    useBBoxHandler([]);
    renderApp("/map");
    expect(await screen.findByText("No meters in this view.")).toBeInTheDocument();
  });

  it("shows an error state", async () => {
    server.use(http.get("*/api/v1/geo/bbox", () => HttpResponse.json(errorBody("internal_error", "Map exploded"), { status: 500 })));
    renderApp("/map");
    expect(await screen.findByText("Map exploded", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("shows the syncing notice on 409 and Retry recovers", async () => {
    let n = 0;
    server.use(
      http.get("*/api/v1/geo/bbox", () => {
        n += 1;
        return n === 1
          ? HttpResponse.json(errorBody("index_not_ready", "Index not ready"), { status: 409 })
          : HttpResponse.json(bboxResponse([bboxMeter()]));
      }),
    );
    renderApp("/map?status=faulty");
    expect(await screen.findByText(/still syncing/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("1 meter in view")).toBeInTheDocument();
  });

  it("near search: typed coordinates call /geo/near, draw the circle, list sorted by distance, click pans", async () => {
    useBBoxHandler();
    server.use(
      http.get("*/api/v1/geo/near", ({ request }) => {
        nearCalls.push(new URL(request.url).searchParams);
        return HttpResponse.json({ items: [nearMeter(0.9, { meter_id: "J2" }), nearMeter(0.12345, { meter_id: "J1", install_status: "faulty" })] });
      }),
    );
    renderApp("/map?make=HPL");
    await screen.findByTestId("map");
    await userEvent.type(screen.getByLabelText("Latitude"), "26.91");
    await userEvent.type(screen.getByLabelText("Longitude"), "75.79");
    const radius = screen.getByLabelText("Radius (km)");
    await userEvent.clear(radius);
    await userEvent.type(radius, "2.5");
    await userEvent.click(screen.getByRole("button", { name: "Find nearby meters" }));
    const list = await screen.findByRole("list", { name: "Nearby meters" });
    expect(nearCalls[0]!.get("lat")).toBe("26.91");
    expect(nearCalls[0]!.get("radius_km")).toBe("2.5");
    expect(nearCalls[0]!.getAll("make")).toEqual(["HPL"]);
    const rows = within(list).getAllByRole("listitem");
    expect(rows[0]!).toHaveTextContent("J1");
    expect(rows[0]!).toHaveTextContent("0.123 km");
    expect(rows[0]!).toHaveTextContent("faulty");
    expect(rows[1]!).toHaveTextContent("J2");
    expect(screen.getByTestId("radius-circle")).toHaveAttribute("data-radius", "2500");
    await userEvent.click(within(rows[0]!).getByRole("button"));
    expect(fake.panTo).toHaveBeenCalledWith([26.91, 75.79]);
  });

  it("near search: clicking the map picks the point and searches with the default 1 km", async () => {
    useBBoxHandler();
    server.use(
      http.get("*/api/v1/geo/near", ({ request }) => {
        nearCalls.push(new URL(request.url).searchParams);
        return HttpResponse.json({ items: [] });
      }),
    );
    renderApp("/map");
    await screen.findByTestId("map");
    act(() => fake.fire("click", { latlng: { lat: 26.9, lng: 75.8 } }));
    expect(await screen.findByText("No meters within that radius.")).toBeInTheDocument();
    expect(screen.getByLabelText("Latitude")).toHaveValue("26.90000");
    expect(nearCalls[0]!.get("radius_km")).toBe("1");
  });

  it("near search validates radius and coordinates without calling the API", async () => {
    useBBoxHandler();
    renderApp("/map");
    await screen.findByTestId("map");
    await userEvent.click(screen.getByRole("button", { name: "Find nearby meters" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/latitude/i);
    fireEvent.change(screen.getByLabelText("Latitude"), { target: { value: "26.9" } });
    fireEvent.change(screen.getByLabelText("Longitude"), { target: { value: "75.8" } });
    fireEvent.change(screen.getByLabelText("Radius (km)"), { target: { value: "75" } });
    await userEvent.click(screen.getByRole("button", { name: "Find nearby meters" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Radius must be between 0.1 and 50 km.");
    expect(nearCalls).toHaveLength(0);
  });

  it("near search shows an API error", async () => {
    useBBoxHandler();
    server.use(http.get("*/api/v1/geo/near", () => HttpResponse.json(errorBody("internal_error", "Near failed"), { status: 500 })));
    renderApp("/map");
    await screen.findByTestId("map");
    act(() => fake.fire("click", { latlng: { lat: 26.9, lng: 75.8 } }));
    expect(await screen.findByText("Near failed", {}, { timeout: 3000 })).toBeInTheDocument();
  });

  it("lists meters in view under the map with a +N more tail", async () => {
    const many = Array.from({ length: 53 }, (_, i) => bboxMeter({ meter_id: `J${100000 + i}`, install_status: i === 1 ? "faulty" : "installed" }));
    useBBoxHandler(many);
    renderApp("/map");
    const list = await screen.findByRole("list", { name: "Meters in view" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(51);
    expect(within(rows[0]!).getByRole("link", { name: "J100000" })).toHaveAttribute("href", "/meters/J100000");
    expect(rows[1]!).toHaveTextContent("faulty");
    expect(rows[50]!).toHaveTextContent("+3 more");
  });

  it("sends the limit and the truncated banner reports the returned count", async () => {
    useBBoxHandler([bboxMeter(), bboxMeter({ meter_id: "J2" })], true);
    renderApp("/map");
    expect(await screen.findByText(/Showing first 2, zoom in/)).toBeInTheDocument();
    expect(bboxCalls[0]!.get("limit")).toBe("1000");
  });

  it("409 notice offers Clear filters when filters are set, and it recovers", async () => {
    server.use(
      http.get("*/api/v1/geo/bbox", ({ request }) =>
        new URL(request.url).searchParams.has("status")
          ? HttpResponse.json(errorBody("index_not_ready", "Index not ready"), { status: 409 })
          : HttpResponse.json(bboxResponse([bboxMeter()])),
      ),
    );
    const { router } = renderApp("/map?status=faulty");
    expect(await screen.findByText(/still syncing/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(await screen.findByText("1 meter in view")).toBeInTheDocument();
    expect(router.search).toBe("");
  });
});
