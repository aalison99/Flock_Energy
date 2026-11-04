import type { ReactNode } from "react";

export type BadgeTone = "installed" | "faulty" | "decommissioned" | "neutral" | "danger" | "info";

const TONES: Record<BadgeTone, string> = {
  installed: "bg-installed-soft text-installed",
  faulty: "bg-faulty-soft text-faulty",
  decommissioned: "bg-decommissioned-soft text-decommissioned",
  neutral: "bg-slate-100 text-slate-600",
  danger: "bg-red-100 text-red-700",
  info: "bg-sky-100 text-sky-700",
};

export function Badge({ tone = "neutral", children }: { tone?: BadgeTone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}>
      {children}
    </span>
  );
}
