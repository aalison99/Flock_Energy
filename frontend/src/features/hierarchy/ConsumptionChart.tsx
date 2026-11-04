import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatDateTime, formatShortDate } from "../../shared/format";
import { toConsumptionRows } from "./chart-data";
import type { ConsumptionRow } from "./chart-data";
import type { Consumption } from "./types";

export default function ConsumptionChart({ data }: { data: Consumption }) {
  const tick = (t: string) => (data.resolution === "daily" ? formatShortDate(t) : formatDateTime(t));
  const rows = toConsumptionRows(data);
  return (
    <div className="h-64 w-full rounded-lg border border-slate-200 bg-white p-3" data-testid="consumption-chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="t" tickFormatter={tick} minTickGap={32} fontSize={11} />
          <YAxis fontSize={11} label={{ value: "kWh", angle: -90, position: "insideLeft", fontSize: 11 }} />
          <Tooltip
            labelFormatter={(t) => formatDateTime(String(t))}
            formatter={(v, name, item) => {
              const r = item.payload as ConsumptionRow;
              return [`${Number(v).toFixed(1)} kWh (${r.meters} of ${r.included} meters)`, name];
            }}
          />
          <Legend />
          <Bar dataKey="full" stackId="k" name="kWh" fill="#0284c7" isAnimationActive={false} />
          <Bar dataKey="partial" stackId="k" name="partial day/hour (fewer meters reporting)" fill="#bae6fd" isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
