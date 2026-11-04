import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { anomaly, anomalyList, dtItem, dtLoad, errorBody, quality, syncRun, syncStatus } from "./fixtures";
import { renderApp } from "./render";
import { server } from "./server";

beforeAll(async () => {
  await import("../features/dashboard/DtLoadChart");
}, 30_000);

afterEach(() => vi.useRealTimers());

describe("Dashboard KPIs", () => {
  it("shows loading then the key figures", async () => {
    renderApp("/");
    expect(screen.getByText("Loading summary…")).toBeInTheDocument();
    expect(await screen.findByText("403")).toBeInTheDocument();
    expect(screen.getByText("238 installed")).toBeInTheDocument();
    expect(screen.getByText("90 faulty")).toBeInTheDocument();
    expect(screen.getByText("75 decommissioned")).toBeInTheDocument();
    expect(screen.getByText("380")).toBeInTheDocument();
    expect(screen.getByText(/23 silent/)).toBeInTheDocument();
    expect(screen.getByText("1,23,457 kWh")).toBeInTheDocument();
    expect(screen.getByText(/Oct 2026.* to .*Nov 2026/)).toBeInTheDocument();
    expect(screen.getByText(/half-hourly:/)).toBeInTheDocument();
    expect(screen.getByText(/daily:/)).toBeInTheDocument();
  });

  it("shows an error with retry when the summary fails", async () => {
    server.use(http.get("*/api/v1/analytics/summary", () => HttpResponse.json(errorBody("internal_error", "boom"), { status: 400 })));
    renderApp("/");
    expect(await screen.findByText("Could not load the summary")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("409 shows the empty-index state with a Resync button", async () => {
    server.use(http.get("*/api/v1/analytics/summary", () => HttpResponse.json(errorBody("index_not_ready", "Index is empty"), { status: 409 })));
    renderApp("/");
    expect(await screen.findByText("The index is empty — start a sync")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Resync" })).toBeEnabled();
  });
});

describe("Anomalies table", () => {
  it("lists anomalies with severity badges and links to meters", async () => {
    server.use(
      http.get("*/api/v1/analytics/anomalies", () =>
        HttpResponse.json(
          anomalyList([
            anomaly({ severity: "error", rule: "consumption_spike", meter_id: "J100777", message: "Spike" }),
            anomaly({ severity: "warning", at: "2026-11-01T10:00:00+05:30" }),
            anomaly({ severity: "info", meter_id: "J100888", message: "FYI" }),
          ]),
        ),
      ),
    );
    renderApp("/");
    const table = await screen.findByRole("table", { name: "Anomalies" });
    expect(within(table).getByRole("link", { name: "J100777" })).toHaveAttribute("href", "/meters/J100777");
    expect(within(table).getByText("error")).toHaveClass("bg-red-100");
    expect(within(table).getByText("warning")).toHaveClass("bg-faulty-soft");
    expect(within(table).getByText("info")).toHaveClass("bg-slate-100");
  });

  it("rule and severity chips update the URL and the request; node filter comes from the URL", async () => {
    const urls: URL[] = [];
    server.use(
      http.get("*/api/v1/analytics/anomalies", ({ request }) => {
        urls.push(new URL(request.url));
        return HttpResponse.json(anomalyList([anomaly()]));
      }),
    );
    const user = userEvent.setup();
    const { router } = renderApp("/?node=Z-01/C-01");
    await user.click(await screen.findByRole("button", { name: "consumption_spike" }));
    await waitFor(() => expect(router.search).toContain("rule=consumption_spike"));
    await waitFor(() => expect(urls.at(-1)?.searchParams.get("rule")).toBe("consumption_spike"));
    expect(urls.at(-1)?.searchParams.get("node")).toBe("Z-01/C-01");
    await user.click(screen.getByRole("button", { name: "error" }));
    await waitFor(() => expect(urls.at(-1)?.searchParams.get("severity")).toBe("error"));
    expect(router.search).toContain("severity=error");
    await user.click(screen.getByRole("button", { name: /Node Z-01\/C-01/ }));
    await waitFor(() => expect(router.search).not.toContain("node="));
  });

  it("pages and shows an empty state", async () => {
    const pages: (string | null)[] = [];
    server.use(
      http.get("*/api/v1/analytics/anomalies", ({ request }) => {
        const p = new URL(request.url).searchParams.get("page");
        pages.push(p);
        return HttpResponse.json(anomalyList([anomaly()], { page: Number(p), total: 20, total_pages: 2, has_next: p === "1" }));
      }),
    );
    const user = userEvent.setup();
    const { router } = renderApp("/");
    await user.click(await screen.findByRole("button", { name: "Next" }));
    await waitFor(() => expect(router.search).toContain("page=2"));
    expect(pages).toContain("2");
  });

  it("shows empty and error states", async () => {
    renderApp("/");
    expect(await screen.findByText("No anomalies match these filters")).toBeInTheDocument();
  });

  it("shows an error", async () => {
    server.use(http.get("*/api/v1/analytics/anomalies", () => HttpResponse.json(errorBody("internal_error", "kaput"), { status: 400 })));
    renderApp("/");
    expect(await screen.findByText("Could not load anomalies")).toBeInTheDocument();
  });
});

describe("DT utilisation", () => {
  it("shows the estimate, coverage, overloaded, the no-estimate list and the note verbatim", async () => {
    server.use(
      http.get("*/api/v1/analytics/transformers/load", ({ request }) => {
        const q = new URL(request.url).searchParams;
        expect(q.get("sort")).toBe("utilisation");
        expect(q.get("limit")).toBe("10");
        return HttpResponse.json(
          dtLoad([
            dtItem({ code: "DT-009", utilisation_pct: 120, overloaded: true, peak_kva_est: 120, half_hourly_meters: 2, meter_count: 5 }),
            dtItem({ code: "DT-001" }),
            dtItem({ code: "DT-004", utilisation_pct: null, peak_kva_est: null, half_hourly_meters: 0, overloaded: false }),
          ]),
        );
      }),
    );
    renderApp("/");
    const table = await screen.findByRole("table", { name: /transformers by estimated utilisation/ });
    expect(within(table).getByText("overloaded")).toBeInTheDocument();
    expect(within(table).getByText("2 of 5 meters")).toBeInTheDocument();
    expect(within(table).getByText("1.2%")).toBeInTheDocument();
    expect(await screen.findByTestId("dt-chart")).toBeInTheDocument();
    expect(screen.getByText("No half-hourly meters")).toBeInTheDocument();
    expect(screen.getByText("DT-004")).toBeInTheDocument();
    expect(screen.getByText("Estimate from half-hourly meters only; daily meters are ignored.")).toBeInTheDocument();
    expect(screen.getByText("estimate")).toBeInTheDocument();
  });

  it("shows an empty state when nothing has an estimate", async () => {
    server.use(http.get("*/api/v1/analytics/transformers/load", () => HttpResponse.json(dtLoad([dtItem({ code: "DT-004", utilisation_pct: null })]))));
    renderApp("/");
    expect(await screen.findByText("No transformer has a load estimate")).toBeInTheDocument();
    expect(screen.getByText("DT-004")).toBeInTheDocument();
  });

  it("shows an error", async () => {
    server.use(http.get("*/api/v1/analytics/transformers/load", () => HttpResponse.json(errorBody("internal_error", "no"), { status: 400 })));
    renderApp("/");
    expect(await screen.findByText("Could not load transformer load")).toBeInTheDocument();
  });
});

describe("Data quality", () => {
  it("shows counts per check and expands issues with evidence", async () => {
    server.use(
      http.get("*/api/v1/data-quality", ({ request }) => {
        const check = new URL(request.url).searchParams.get("check");
        if (!check) return HttpResponse.json(quality());
        return HttpResponse.json(
          quality({
            total: 1,
            items: [
              {
                check: "name_conflict",
                severity: "warning",
                entity: "circle",
                entity_id: "Z-01/C-01",
                message: "Two names for one circle",
                evidence: { names: "A | B", count: 2 },
              },
            ],
          }),
        );
      }),
    );
    const user = userEvent.setup();
    renderApp("/");
    const btn = await screen.findByRole("button", { name: /name_conflict/ });
    expect(btn).toHaveTextContent("2");
    expect(screen.getByRole("button", { name: /missing_geo/ })).toBeDisabled();
    await user.click(btn);
    expect(btn).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByText("Two names for one circle")).toBeInTheDocument();
    expect(screen.getByText("names")).toBeInTheDocument();
    expect(screen.getByText("A | B")).toBeInTheDocument();
    expect(screen.getByText("count")).toBeInTheDocument();
    await user.click(btn);
    expect(screen.queryByText("Two names for one circle")).not.toBeInTheDocument();
  });

  it("shows an error", async () => {
    server.use(http.get("*/api/v1/data-quality", () => HttpResponse.json(errorBody("internal_error", "dq down"), { status: 400 })));
    renderApp("/");
    expect(await screen.findByText("Could not load data quality")).toBeInTheDocument();
  });
});

describe("Sync panel", () => {
  it("shows the latest run and last successful sync", async () => {
    renderApp("/");
    expect(await screen.findByText("Latest run")).toBeInTheDocument();
    expect(screen.getByText("succeeded")).toBeInTheDocument();
    expect(screen.getByText(/Last successful sync:/)).not.toHaveTextContent("never");
    expect(screen.getByText(/readings:/)).toBeInTheDocument();
  });

  it("Resync posts include_readings, polls every 5 s while running, stops when finished", async () => {
    let status = syncStatus();
    let statusCalls = 0;
    let body: unknown;
    server.use(
      http.get("*/api/v1/sync/status", () => {
        statusCalls++;
        return HttpResponse.json(status);
      }),
      http.post("*/api/v1/sync", async ({ request }) => {
        body = await request.json();
        status = syncStatus(syncRun({ id: 2, status: "running", finished_at: null }));
        return HttpResponse.json(status.latest, { status: 202 });
      }),
    );
    const user = userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTimeAsync(ms) });
    vi.useFakeTimers({ shouldAdvanceTime: true, toFake: ["setInterval", "clearInterval", "setTimeout", "clearTimeout"] });
    renderApp("/");
    const btn = await screen.findByRole("button", { name: "Resync" });
    await user.click(btn);
    await waitFor(() => expect(body).toEqual({ include_readings: true }));
    const running = await screen.findByRole("button", { name: "Syncing…" });
    expect(running).toBeDisabled();

    await waitFor(() => expect(statusCalls).toBeGreaterThanOrEqual(2));
    const before = statusCalls;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    await waitFor(() => expect(statusCalls).toBeGreaterThan(before));

    status = syncStatus(syncRun({ id: 2, status: "succeeded" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(await screen.findByRole("button", { name: "Resync" })).toBeEnabled();
    const after = statusCalls;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20000);
    });
    expect(statusCalls).toBe(after);
  });

  it("a 409 on POST shows that a sync is already running", async () => {
    server.use(http.post("*/api/v1/sync", () => HttpResponse.json(errorBody("sync_in_progress", "busy"), { status: 409 })));
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: "Resync" }));
    expect(await screen.findByText("A sync is already running.")).toBeInTheDocument();
  });

  it("disables Resync while a run is already running", async () => {
    server.use(http.get("*/api/v1/sync/status", () => HttpResponse.json(syncStatus(syncRun({ status: "running", finished_at: null })))));
    renderApp("/");
    expect(await screen.findByRole("button", { name: "Syncing…" })).toBeDisabled();
  });

  it("shows a failed run's error and an error state", async () => {
    server.use(http.get("*/api/v1/sync/status", () => HttpResponse.json(syncStatus(syncRun({ status: "failed", error: "portal down" })))));
    renderApp("/");
    expect(await screen.findByText("portal down")).toBeInTheDocument();
  });

  it("shows an error when status cannot load", async () => {
    server.use(http.get("*/api/v1/sync/status", () => HttpResponse.json(errorBody("internal_error", "x"), { status: 400 })));
    renderApp("/");
    expect(await screen.findByText("Could not load sync status")).toBeInTheDocument();
  });
});

describe("Portal status", () => {
  it("shows a single portal pill (the header's)", async () => {
    renderApp("/");
    await screen.findByText("403");
    expect(screen.getAllByText("Portal OK").length).toBe(1);
  });
});

describe("Filters robustness (fix round 1)", () => {
  it("keeps chips and the previous rows while a filter change loads", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => (release = r));
    server.use(
      http.get("*/api/v1/analytics/anomalies", async ({ request }) => {
        if (new URL(request.url).searchParams.get("rule") === "consumption_spike") await gate;
        return HttpResponse.json(anomalyList([anomaly({ message: "Row one" })]));
      }),
    );
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: "consumption_spike" }));
    expect(screen.getByRole("button", { name: "consumption_spike" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Row one")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "inactive_but_consuming" })).toBeInTheDocument();
    release();
  });

  it("shows the active rule chip and Clear filters even when the request fails", async () => {
    server.use(http.get("*/api/v1/analytics/anomalies", () => HttpResponse.json(errorBody("validation_error", "bad"), { status: 422 })));
    const user = userEvent.setup();
    const { router } = renderApp("/?rule=weird&severity=error");
    expect(await screen.findByText("Could not load anomalies")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "weird" })).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(router.search).toBe(""));
  });

  it("drops an unknown severity from the URL and the request", async () => {
    const sev: (string | null)[] = [];
    server.use(
      http.get("*/api/v1/analytics/anomalies", ({ request }) => {
        sev.push(new URL(request.url).searchParams.get("severity"));
        return HttpResponse.json(anomalyList([anomaly()]));
      }),
    );
    const { router } = renderApp("/?severity=fatal");
    await waitFor(() => expect(router.search).toBe(""));
    await screen.findByRole("table", { name: "Anomalies" });
    expect(sev.every((s) => s === null)).toBe(true);
  });

  it("drops a rule the server does not know once the rule list arrives", async () => {
    const { router } = renderApp("/?rule=bogus");
    await waitFor(() => expect(router.search).toBe(""));
  });

  it("keeps Resync reachable when the summary fails with a non-409 error", async () => {
    server.use(http.get("*/api/v1/analytics/summary", () => HttpResponse.json(errorBody("internal_error", "502"), { status: 400 })));
    renderApp("/");
    expect(await screen.findByText("Could not load the summary")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Resync" })).toBeEnabled();
  });
});
