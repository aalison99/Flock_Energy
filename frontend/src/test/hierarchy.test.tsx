import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeAll, describe, expect, it } from "vitest";
import { toConsumptionRows } from "../features/hierarchy/chart-data";
import { consumption, errorBody, meterPage, meterSummary, nodeDetail, quality, treeNode, treeResponse } from "./fixtures";
import { renderApp } from "./render";
import { server } from "./server";

beforeAll(async () => {
  await import("../features/hierarchy/ConsumptionChart");
}, 30_000);

describe("Hierarchy explorer", () => {
  it("renders zones with counts, breakdown bars and an unplaced tag", async () => {
    server.use(
      http.get("*/api/v1/hierarchy", () =>
        HttpResponse.json(treeResponse([treeNode({ unplaced_count: 3 }), treeNode({ id: "Z-02", code: "Z-02", name: "Jaipur Zone 2", meter_count: 4 })])),
      ),
    );
    renderApp("/hierarchy");
    expect(screen.getByText("Loading hierarchy…")).toBeInTheDocument();
    const tree = await screen.findByRole("navigation", { name: "Hierarchy tree" });
    expect(within(tree).getByText("Jaipur Zone 1")).toBeInTheDocument();
    expect(within(tree).getByText("10 meters")).toBeInTheDocument();
    expect(within(tree).getByText("3 unplaced")).toBeInTheDocument();
    const bars = within(tree).getAllByRole("img", { name: /^Status:/ });
    expect(bars[0]!).toHaveAccessibleName("Status: 8 installed, 1 faulty, 1 decommissioned, 0 unknown");
    expect(bars[0]!.querySelector('[data-segment="faulty"]')).not.toBeNull();
    expect(bars[0]!.querySelector('[data-segment="unknown"]')).toBeNull();
  });

  it("expanding a preloaded node shows children without fetching; expanding a circle fetches the node", async () => {
    const nodeCalls: (string | null)[] = [];
    server.use(
      http.get("*/api/v1/hierarchy/node", ({ request }) => {
        nodeCalls.push(new URL(request.url).searchParams.get("id"));
        return HttpResponse.json(nodeDetail());
      }),
    );
    const user = userEvent.setup();
    renderApp("/hierarchy");
    const zone = await screen.findByRole("button", { name: "Expand Jaipur Zone 1" });
    expect(zone).toHaveAttribute("aria-expanded", "false");
    await user.click(zone);
    expect(zone).toHaveAttribute("aria-expanded", "true");
    const circle = await screen.findByRole("button", { name: "Expand Circle 1" });
    expect(screen.getByText("2 unplaced")).toBeInTheDocument();
    nodeCalls.length = 0;
    await user.click(circle);
    expect(await screen.findByRole("button", { name: /^Division 1/ })).toBeInTheDocument();
    expect(nodeCalls).toContain("Z-01/C-01");
    expect(new Set(nodeCalls).size).toBe(1);
  });

  it("selecting a node updates ?node= and loads detail, consumption and meters", async () => {
    const consumptionUrls: URL[] = [];
    server.use(
      http.get("*/api/v1/analytics/consumption", ({ request }) => {
        consumptionUrls.push(new URL(request.url));
        return HttpResponse.json(consumption());
      }),
      http.get("*/api/v1/analytics/anomalies", () => HttpResponse.json({ items: [], page: 1, page_size: 1, total: 7, total_pages: 7, has_next: true, rules: [] })),
      http.get("*/api/v1/hierarchy/node/meters", () => HttpResponse.json(meterPage([meterSummary({ meter_id: "J100123" })]))),
    );
    const user = userEvent.setup();
    const { router } = renderApp("/hierarchy");
    await user.click(await screen.findByRole("button", { name: "Expand Jaipur Zone 1" }));
    await user.click(await screen.findByRole("button", { name: /^Circle 1/ }));
    await waitFor(() => expect(decodeURIComponent(router.search)).toContain("node=Z-01/C-01"));
    const crumbs = await screen.findByRole("navigation", { name: "Node path" });
    expect(crumbs).toHaveTextContent("Jaipur Zone 1");
    expect(await screen.findByText(/4 meters included, 2 excluded/)).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "J100123" })).toHaveAttribute("href", "/meters/J100123");
    const anomalies = await screen.findByRole("link", { name: /7 anomalies/ });
    expect(anomalies.getAttribute("href")).toBe("/?node=Z-01%2FC-01");
    expect(consumptionUrls[0]!.searchParams.get("node")).toBe("Z-01/C-01");
    expect(consumptionUrls[0]!.searchParams.get("resolution")).toBe("daily");
  });

  it("hourly toggle lives in the URL and changes the request", async () => {
    const seen: (string | null)[] = [];
    server.use(
      http.get("*/api/v1/analytics/consumption", ({ request }) => {
        seen.push(new URL(request.url).searchParams.get("resolution"));
        return HttpResponse.json(consumption());
      }),
    );
    const user = userEvent.setup();
    const { router } = renderApp("/hierarchy?node=Z-01/C-01");
    await user.click(await screen.findByRole("button", { name: "Hourly" }));
    await waitFor(() => expect(router.search).toContain("res=hourly"));
    await waitFor(() => expect(seen).toContain("hourly"));
  });

  it("shows alt-name badge with meter ids and a name-conflict badge", async () => {
    server.use(
      http.get("*/api/v1/hierarchy/node", () =>
        HttpResponse.json(nodeDetail({ alt_names: [{ name: "Cirkle One", meter_ids: ["J100001", "J100002"] }] })),
      ),
      http.get("*/api/v1/data-quality", ({ request }) => {
        expect(new URL(request.url).searchParams.get("check")).toBe("name_conflict");
        return HttpResponse.json(
          quality({
            items: [{ check: "name_conflict", severity: "warning", entity: "circle", entity_id: "Z-01/C-01", message: "x", evidence: {} }],
          }),
        );
      }),
    );
    renderApp("/hierarchy?node=Z-01/C-01");
    expect(await screen.findByText("also called Cirkle One")).toBeInTheDocument();
    expect(screen.getByText("(J100001, J100002)")).toBeInTheDocument();
    expect((await screen.findAllByText("name conflict")).length).toBeGreaterThan(0);
  });

  it("shows a 409 notice for the tree", async () => {
    server.use(http.get("*/api/v1/hierarchy", () => HttpResponse.json(errorBody("index_not_ready", "Index is empty"), { status: 409 })));
    renderApp("/hierarchy");
    expect(await screen.findByText("The index is empty — start a sync")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /start a sync/ })).toHaveAttribute("href", "/");
  });

  it("shows an error with retry for the tree", async () => {
    server.use(http.get("*/api/v1/hierarchy", () => HttpResponse.json(errorBody("internal_error", "boom"), { status: 400 })));
    renderApp("/hierarchy");
    expect(await screen.findByText("Could not load the hierarchy")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows empty states for no zones and no selection", async () => {
    server.use(http.get("*/api/v1/hierarchy", () => HttpResponse.json(treeResponse([]))));
    renderApp("/hierarchy");
    expect(await screen.findByText("No hierarchy yet")).toBeInTheDocument();
  });

  it("asks for a selection when no node is in the URL", async () => {
    renderApp("/hierarchy");
    expect(await screen.findByText("Select a node")).toBeInTheDocument();
  });

  it("handles a missing node and an empty meters list", async () => {
    server.use(http.get("*/api/v1/hierarchy/node", () => HttpResponse.json(errorBody("not_found", "no"), { status: 404 })));
    renderApp("/hierarchy?node=Z-09");
    expect(await screen.findByText("Node not found")).toBeInTheDocument();
  });

  it("shows empty meters and an error for consumption", async () => {
    server.use(
      http.get("*/api/v1/hierarchy/node/meters", () => HttpResponse.json(meterPage([]))),
      http.get("*/api/v1/analytics/consumption", () => HttpResponse.json(errorBody("internal_error", "no data"), { status: 400 })),
    );
    renderApp("/hierarchy?node=Z-01/C-01");
    expect(await screen.findByText("No meters in this node")).toBeInTheDocument();
    expect(await screen.findByText("Could not load consumption")).toBeInTheDocument();
  });

  it("pages the node meters via the URL", async () => {
    const pages: (string | null)[] = [];
    server.use(
      http.get("*/api/v1/hierarchy/node/meters", ({ request }) => {
        const p = new URL(request.url).searchParams.get("page");
        pages.push(p);
        return HttpResponse.json(meterPage([meterSummary()], { page: Number(p), total: 20, total_pages: 2, has_next: p === "1" }));
      }),
    );
    const user = userEvent.setup();
    const { router } = renderApp("/hierarchy?node=Z-01/C-01");
    await user.click(await screen.findByRole("button", { name: "Next" }));
    await waitFor(() => expect(router.search).toContain("mpage=2"));
    expect(pages).toContain("2");
  });

  it("selecting a row does not toggle it; the chevron toggles without selecting", async () => {
    server.use(
      http.get("*/api/v1/hierarchy/node", () =>
        HttpResponse.json(nodeDetail({ id: "Z-01", level: "zone", code: "Z-01", name: "Jaipur Zone 1", path: [{ id: "Z-01", level: "zone", code: "Z-01", name: "Jaipur Zone 1", meter_count: 10 }] })),
      ),
    );
    const user = userEvent.setup();
    const { router } = renderApp("/hierarchy");
    await user.click(await screen.findByRole("button", { name: /^Jaipur Zone 1/ }));
    await waitFor(() => expect(router.search).toContain("node=Z-01"));
    const chevron = screen.getByRole("button", { name: "Expand Jaipur Zone 1" });
    expect(chevron).toHaveAttribute("aria-expanded", "false");
    router.search = "";
    await user.click(chevron);
    expect(screen.getByRole("button", { name: "Collapse Jaipur Zone 1" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.queryByRole("button", { name: /^Circle 1/ })).toBeInTheDocument();
  });

  it("a deep link expands the tree along the node's path", async () => {
    renderApp("/hierarchy?node=Z-01/C-01");
    expect(await screen.findByRole("button", { name: "Collapse Jaipur Zone 1" })).toHaveAttribute("aria-expanded", "true");
    const circle = await screen.findByRole("button", { name: /^Circle 1/ });
    expect(circle).toHaveAttribute("aria-current", "true");
  });

  it("pages through all name conflicts", async () => {
    const pages: (string | null)[] = [];
    server.use(
      http.get("*/api/v1/data-quality", ({ request }) => {
        const p = new URL(request.url).searchParams.get("page");
        pages.push(p);
        const item = (id: string) => ({ check: "name_conflict", severity: "warning" as const, entity: "zone", entity_id: id, message: "x", evidence: {} });
        return HttpResponse.json(
          p === "1" ? quality({ items: [item("Z-02")], has_next: true }) : quality({ items: [item("Z-01")], page: 2 }),
        );
      }),
    );
    renderApp("/hierarchy");
    await screen.findByRole("button", { name: /^Jaipur Zone 1/ });
    await waitFor(() => expect(screen.getAllByText("name conflict").length).toBe(2));
    expect(pages).toEqual(["1", "2"]);
  });
});

describe("toConsumptionRows", () => {
  it("marks buckets with fewer meters than included as partial", () => {
    const rows = toConsumptionRows({
      meters_included: 4,
      items: [
        { start: "a", end: "b", kwh: 10, kvah: null, meters: 4 },
        { start: "b", end: "c", kwh: 6, kvah: null, meters: 3 },
        { start: "c", end: "d", kwh: null, kvah: null, meters: 0 },
      ],
    });
    expect(rows.map((r) => [r.full, r.partial])).toEqual([[10, null], [null, 6], [null, null]]);
    expect(rows[1]).toMatchObject({ meters: 3, included: 4 });
  });
});
