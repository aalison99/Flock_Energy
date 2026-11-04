import { screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { renderApp } from "./render";

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: ReactNode }) => <div data-testid="map">{children}</div>,
  TileLayer: () => null,
  Popup: () => null,
  CircleMarker: () => null,
  Circle: () => null,
  useMap: () => ({ getBounds: () => ({ getSouth: () => 1, getWest: () => 1, getNorth: () => 2, getEast: () => 2 }), panTo: () => {} }),
  useMapEvents: () => null,
}));

// Deliberately no pre-import of the lazy chunk: this file is where the Suspense fallback is exercised.
describe("Map route Suspense", () => {
  it("shows the fallback before the lazy chunk resolves, then the map", async () => {
    renderApp("/map");
    expect(screen.getByText("Loading map…")).toBeInTheDocument();
    expect(await screen.findByTestId("map", {}, { timeout: 10_000 })).toBeInTheDocument();
  }, 20_000);
});
