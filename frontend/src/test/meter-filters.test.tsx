import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { errorBody, facets, meterPage, meterSummary } from "./fixtures";
import { renderApp } from "./render";
import { server } from "./server";

/** Records the query strings of list and facet requests. */
function record() {
  const list: URLSearchParams[] = [];
  const fac: URLSearchParams[] = [];
  server.use(
    http.get("*/api/v1/meters", ({ request }) => {
      list.push(new URL(request.url).searchParams);
      return HttpResponse.json(meterPage([meterSummary()], { total: 238, page: 2, total_pages: 10, has_next: true }));
    }),
    http.get("*/api/v1/meters/facets", ({ request }) => {
      fac.push(new URL(request.url).searchParams);
      return HttpResponse.json(facets());
    }),
  );
  return { list, fac };
}

describe("Explorer filters", () => {
  it("renders facet chips with counts, the DT select sorted by code, and the total", async () => {
    record();
    renderApp("/meters");
    expect(await screen.findByRole("button", { name: "installed (238)" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "HPL (200)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "three (126)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ct_operated (103)" })).toBeInTheDocument();
    const dt = screen.getByLabelText("DT");
    expect(within(dt).getAllByRole("option").map((o) => o.textContent)).toEqual(["All", "DT-001 (20)", "DT-007 (13)"]);
    expect(await screen.findByText("238 meters")).toBeInTheDocument();
  });

  it("hides zero-count chips unless selected", async () => {
    record();
    renderApp("/meters");
    await screen.findByRole("button", { name: "three (126)" });
    expect(screen.queryByRole("button", { name: /^unknown/ })).not.toBeInTheDocument();
  });

  it("keeps a selected value visible even at zero count", async () => {
    server.use(http.get("*/api/v1/meters/facets", () => HttpResponse.json(facets({ phase: { single: 5 } }))));
    renderApp("/meters?phase=three");
    expect(await screen.findByRole("button", { name: "three (0)" })).toHaveAttribute("aria-pressed", "true");
  });

  it("multi-select status serialises repeated keys, updates the URL and resets the page", async () => {
    const { list, fac } = record();
    const { router } = renderApp("/meters?page=2");
    await userEvent.click(await screen.findByRole("button", { name: "installed (238)" }));
    await userEvent.click(screen.getByRole("button", { name: "faulty (90)" }));
    await waitFor(() => expect(router.search).toBe("?status=installed&status=faulty"));
    await waitFor(() => expect(list.at(-1)?.getAll("status")).toEqual(["installed", "faulty"]));
    expect(list.at(-1)?.get("page")).toBe("1");
    await waitFor(() => expect(fac.at(-1)?.getAll("status")).toEqual(["installed", "faulty"]));
    expect(screen.getByRole("button", { name: "installed (238)" })).toHaveAttribute("aria-pressed", "true");
    // toggling off removes it
    await userEvent.click(screen.getByRole("button", { name: "installed (238)" }));
    await waitFor(() => expect(router.search).toBe("?status=faulty"));
  });

  it("single-select phase replaces and toggles off", async () => {
    const { list } = record();
    const { router } = renderApp("/meters");
    await userEvent.click(await screen.findByRole("button", { name: "single (277)" }));
    await waitFor(() => expect(router.search).toBe("?phase=single"));
    await userEvent.click(screen.getByRole("button", { name: "three (126)" }));
    await waitFor(() => expect(router.search).toBe("?phase=three"));
    await waitFor(() => expect(list.at(-1)?.get("phase")).toBe("three"));
    await userEvent.click(screen.getByRole("button", { name: "three (126)" }));
    await waitFor(() => expect(router.search).toBe(""));
  });

  it("DT select and sort select go to the URL and the request", async () => {
    const { list } = record();
    const { router } = renderApp("/meters?page=3");
    await screen.findByRole("button", { name: "installed (238)" });
    await userEvent.selectOptions(screen.getByLabelText("DT"), "DT-007");
    await waitFor(() => expect(router.search).toBe("?dt=DT-007"));
    await userEvent.selectOptions(screen.getByLabelText("Sort"), "-meter_id");
    await waitFor(() => expect(router.search).toBe("?dt=DT-007&sort=-meter_id"));
    await waitFor(() => expect(list.at(-1)?.get("sort")).toBe("-meter_id"));
    expect(list.at(-1)?.get("dt")).toBe("DT-007");
    expect(list.at(-1)?.get("page")).toBe("1");
    await userEvent.selectOptions(screen.getByLabelText("Sort"), "meter_id");
    await waitFor(() => expect(router.search).toBe("?dt=DT-007"));
  });

  it("Clear filters removes chips and selects but keeps search and sort", async () => {
    const { list } = record();
    const { router } = renderApp("/meters?q=SE&status=faulty&make=HPL&dt=DT-001&sort=make&page=2");
    await waitFor(() => expect(list.at(-1)?.getAll("make")).toEqual(["HPL"]));
    await userEvent.click(await screen.findByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(router.search).toBe("?q=SE&sort=make"));
    expect(screen.queryByRole("button", { name: "Clear filters" })).not.toBeInTheDocument();
  });

  it("409 with filters shows the notice with Clear filters, hides the FilterBar, and recovers", async () => {
    server.use(
      http.get("*/api/v1/meters", ({ request }) =>
        new URL(request.url).searchParams.has("status")
          ? HttpResponse.json(errorBody("index_not_ready", "Index not ready: sync in progress"), { status: 409 })
          : HttpResponse.json(meterPage([meterSummary()])),
      ),
    );
    const { router } = renderApp("/meters?status=faulty");
    expect(await screen.findByText(/still syncing/)).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Filters" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Search meters")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(await screen.findByRole("link", { name: "J100000" })).toBeInTheDocument();
    expect(router.search).toBe("");
    expect(screen.getByRole("group", { name: "Filters" })).toBeInTheDocument();
  });

  it("View on map link carries the filters", async () => {
    record();
    renderApp("/meters?status=faulty&status=installed&dt=DT-001&sort=make&page=2");
    const link = await screen.findByRole("link", { name: "View on map" });
    expect(link).toHaveAttribute("href", "/map?status=faulty&status=installed&dt=DT-001");
  });

  it("shows a loading line while facets load", async () => {
    server.use(
      http.get("*/api/v1/meters/facets", async () => {
        await new Promise((r) => setTimeout(r, 150));
        return HttpResponse.json(facets());
      }),
    );
    renderApp("/meters");
    expect(await screen.findByText("Loading filters…")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "installed (238)" })).toBeInTheDocument();
    expect(screen.queryByText("Loading filters…")).not.toBeInTheDocument();
  });

  it("shows the server message and Retry when facets fail, and the table stays usable", async () => {
    let n = 0;
    server.use(
      http.get("*/api/v1/meters/facets", () => {
        n += 1;
        return n === 1 ? HttpResponse.json(errorBody("bad_request", "Facets broke"), { status: 400 }) : HttpResponse.json(facets());
      }),
    );
    renderApp("/meters");
    expect(await screen.findByText("Facets broke")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "J100000" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry filters" }));
    expect(await screen.findByRole("button", { name: "installed (238)" })).toBeInTheDocument();
  });

  it("drops unknown enum values from the URL and never sends them", async () => {
    const { list, fac } = record();
    const { router } = renderApp("/meters?status=bogus&status=faulty&phase=x&install_type=y&sort=nope&make=HPL");
    await waitFor(() => expect(router.search).toBe("?make=HPL&status=faulty"));
    await screen.findByRole("button", { name: "installed (238)" });
    for (const q of [...list, ...fac].slice(-2)) {
      expect(q.getAll("status")).toEqual(["faulty"]);
      expect(q.has("phase")).toBe(false);
      expect(q.has("install_type")).toBe(false);
      expect(q.has("sort") && q.get("sort") !== "meter_id").toBe(false);
    }
  });
});
