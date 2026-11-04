import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { errorBody, meterPage, meterSummary } from "./fixtures";
import { currentSearch, renderApp } from "./render";
import { server } from "./server";

describe("Meters explorer", () => {
  it("shows loading then rows", async () => {
    server.use(
      http.get("*/api/v1/meters", () =>
        HttpResponse.json(meterPage([meterSummary(), meterSummary({ meter_id: "J100001", install_status: "faulty", dt_code: null })])),
      ),
    );
    renderApp("/meters");
    expect(screen.getByText("Loading meters…")).toBeInTheDocument();
    const link = await screen.findByRole("link", { name: "J100000" });
    expect(link).toHaveAttribute("href", "/meters/J100000");
    const row = screen.getByRole("link", { name: "J100001" }).closest("tr")!;
    expect(within(row).getByText("faulty")).toBeInTheDocument();
    expect(within(row).getByText("—")).toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    server.use(http.get("*/api/v1/meters", () => HttpResponse.json(meterPage([]))));
    renderApp("/meters?q=zzz");
    expect(await screen.findByText("No meters found")).toBeInTheDocument();
  });

  it("shows an error state", async () => {
    server.use(http.get("*/api/v1/meters", () => HttpResponse.json(errorBody("portal_unavailable", "Portal is down"), { status: 503 })));
    renderApp("/meters");
    expect(await screen.findByText("Portal is down", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("shows an honest notice with the server message on 409, and Retry refetches", async () => {
    let calls = 0;
    server.use(
      http.get("*/api/v1/meters", () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json(errorBody("index_not_ready", "Index not ready: sync in progress"), { status: 409 })
          : HttpResponse.json(meterPage([meterSummary()]));
      }),
    );
    renderApp("/meters");
    expect(await screen.findByText(/The local index is still syncing, so this view isn't available yet\./)).toBeInTheDocument();
    expect(screen.getByText("Index not ready: sync in progress")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("link", { name: "J100000" })).toBeInTheDocument();
  });

  it("clamps an out-of-range page in the URL to the last page", async () => {
    server.use(
      http.get("*/api/v1/meters", ({ request }) => {
        const page = Number(new URL(request.url).searchParams.get("page"));
        return page > 3
          ? HttpResponse.json(meterPage([], { page, total: 60, total_pages: 3 }))
          : HttpResponse.json(meterPage([meterSummary()], { page, total: 60, total_pages: 3 }));
      }),
    );
    const { router } = renderApp("/meters?page=999");
    await waitFor(() => expect(currentSearch(router)).toBe("?page=3"));
    expect(await screen.findByRole("link", { name: "J100000" })).toBeInTheDocument();
  });

  it("table has a caption and column scopes", async () => {
    renderApp("/meters");
    const table = await screen.findByRole("table", { name: "Meters" });
    expect(within(table).getAllByRole("columnheader")[0]).toHaveAttribute("scope", "col");
  });

  it("search debounces, updates the URL and the request", async () => {
    const seen: (string | null)[] = [];
    server.use(
      http.get("*/api/v1/meters", ({ request }) => {
        seen.push(new URL(request.url).searchParams.get("q"));
        return HttpResponse.json(meterPage([meterSummary()]));
      }),
    );
    const { router } = renderApp("/meters");
    await screen.findByRole("link", { name: "J100000" });
    await userEvent.type(screen.getByLabelText("Search meters"), "SE33");
    await waitFor(() => expect(currentSearch(router)).toBe("?q=SE33"));
    await waitFor(() => expect(seen).toContain("SE33"));
    // Debounced: the intermediate strings never became requests.
    expect(seen).not.toContain("S");
    expect(seen).not.toContain("SE");
  });

  it("restores q and page from the URL", async () => {
    const seen: URLSearchParams[] = [];
    server.use(
      http.get("*/api/v1/meters", ({ request }) => {
        seen.push(new URL(request.url).searchParams);
        return HttpResponse.json(meterPage([meterSummary()], { page: 2, total_pages: 3, total: 60, has_next: true }));
      }),
    );
    renderApp("/meters?q=abc&page=2");
    await screen.findByRole("link", { name: "J100000" });
    expect(screen.getByLabelText("Search meters")).toHaveValue("abc");
    expect(seen[0]?.get("q")).toBe("abc");
    expect(seen[0]?.get("page")).toBe("2");
    expect(seen[0]?.get("page_size")).toBe("25");
  });

  it("page change updates the URL and the request", async () => {
    const pages: (string | null)[] = [];
    server.use(
      http.get("*/api/v1/meters", ({ request }) => {
        const page = new URL(request.url).searchParams.get("page");
        pages.push(page);
        return HttpResponse.json(meterPage([meterSummary()], { page: Number(page), total: 60, total_pages: 3, has_next: Number(page) < 3 }));
      }),
    );
    const { router } = renderApp("/meters");
    await screen.findByRole("link", { name: "J100000" });
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(currentSearch(router)).toBe("?page=2"));
    await waitFor(() => expect(pages).toContain("2"));
  });
});
