import { Outlet, useRoutes } from "react-router";
import type { RouteObject } from "react-router";
import { HealthPill } from "../features/health";
import { DashboardRoute } from "../routes/DashboardRoute";
import { HierarchyRoute } from "../routes/HierarchyRoute";
import { MeterDetailRoute } from "../routes/MeterDetailRoute";
import { MapRoute } from "../routes/MapRoute";
import { MetersRoute } from "../routes/MetersRoute";
import { Placeholder } from "../routes/Placeholder";
import { Layout } from "../shared";

function Shell() {
  return (
    <Layout headerSlot={<HealthPill />}>
      <Outlet />
    </Layout>
  );
}

export const routes: RouteObject[] = [
  {
    element: <Shell />,
    children: [
      { path: "/", element: <DashboardRoute /> },
      { path: "/meters", element: <MetersRoute /> },
      { path: "/meters/:meterId", element: <MeterDetailRoute /> },
      { path: "/map", element: <MapRoute /> },
      { path: "/hierarchy", element: <HierarchyRoute /> },
      { path: "*", element: <Placeholder title="Page not found" /> },
    ],
  },
];

/** Rendered inside a Router (BrowserRouter in the app, MemoryRouter in tests). */
export function AppRoutes() {
  return useRoutes(routes);
}
