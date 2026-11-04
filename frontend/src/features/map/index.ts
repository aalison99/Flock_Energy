import { lazy } from "react";

/** Leaflet is heavy, so the map view is its own chunk; render it inside <Suspense>. */
export const MeterMap = lazy(() => import("./MeterMapView"));
