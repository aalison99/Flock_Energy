import type { ReactNode } from "react";
import { NavLink } from "react-router";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/meters", label: "Meters", end: false },
  { to: "/map", label: "Map", end: false },
  { to: "/hierarchy", label: "Hierarchy", end: false },
];

/** App chrome. `headerSlot` lets the app root put feature widgets (e.g. health) in the header. */
export function Layout({ headerSlot, children }: { headerSlot?: ReactNode; children: ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-6">
            <span className="text-lg font-semibold tracking-tight">Urja Meters</span>
            <nav aria-label="Main" className="flex gap-1">
              {NAV.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `rounded px-3 py-1.5 text-sm font-medium ${
                      isActive ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
          {headerSlot}
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
    </div>
  );
}
