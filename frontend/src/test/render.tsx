import { render } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { makeQueryClient, Providers } from "../app/providers";
import { AppRoutes } from "../app/router";

interface Probe {
  search: string;
  pathname: string;
}

/** Render the real app (providers + routes + layout) at a URL; `router.search` reflects the live URL. */
export function renderApp(url: string) {
  const probe: Probe = { search: "", pathname: "" };
  function LocationProbe() {
    const loc = useLocation();
    probe.search = loc.search;
    probe.pathname = loc.pathname;
    return null;
  }
  const utils = render(
    <Providers client={makeQueryClient()}>
      <MemoryRouter initialEntries={[url]}>
        <LocationProbe />
        <AppRoutes />
      </MemoryRouter>
    </Providers>,
  );
  return { router: probe, ...utils };
}

export const currentSearch = (router: Probe) => router.search;
