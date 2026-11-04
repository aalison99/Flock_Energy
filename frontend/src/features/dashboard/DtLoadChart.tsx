import { Bar, BarChart, Cell, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DtLoadItem } from "./types";

/** Horizontal bars of utilisation_pct against a 100% capacity line. Overloaded DTs are red. */
export default function DtLoadChart({ items }: { items: DtLoadItem[] }) {
  const max = Math.max(100, ...items.map((i) => i.utilisation_pct ?? 0));
  const rows = items.map((i) => ({ code: i.code, pct: i.utilisation_pct, overloaded: i.overloaded }));
  return (
    <div className="w-full rounded-lg border border-slate-200 bg-white p-3" style={{ height: 40 + rows.length * 28 }} data-testid="dt-chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
          <XAxis type="number" domain={[0, Math.ceil(max * 1.05)]} unit="%" fontSize={11} />
          <YAxis type="category" dataKey="code" width={64} fontSize={11} />
          <Tooltip formatter={(v) => [`${Number(v).toFixed(2)}% (estimate)`, "Utilisation"]} />
          <ReferenceLine x={100} stroke="#b91c1c" strokeDasharray="4 2" label={{ value: "capacity", fontSize: 11, position: "top" }} />
          <Bar dataKey="pct" isAnimationActive={false}>
            {rows.map((r) => (
              <Cell key={r.code} fill={r.overloaded ? "#dc2626" : "#0284c7"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
