import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatDateTime, formatShortDate } from "../../shared/format";
import type { ChartPoint, Resolution } from "./types";

export default function ReadingsChart({ data, resolution }: { data: ChartPoint[]; resolution: Resolution }) {
  const tick = (t: string) => (resolution === "daily" ? formatShortDate(t) : formatDateTime(t));
  return (
    <div className="h-72 w-full rounded-lg border border-slate-200 bg-white p-3" data-testid="readings-chart">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="t" tickFormatter={tick} minTickGap={32} fontSize={11} />
          <YAxis yAxisId="kwh" fontSize={11} label={{ value: "kWh", angle: -90, position: "insideLeft", fontSize: 11 }} />
          <YAxis
            yAxisId="volt"
            orientation="right"
            domain={["auto", "auto"]}
            fontSize={11}
            label={{ value: "V", angle: 90, position: "insideRight", fontSize: 11 }}
          />
          <Tooltip labelFormatter={(t) => formatDateTime(String(t))} />
          <Legend />
          <Bar yAxisId="kwh" dataKey="kwh" name="kWh" fill="#0284c7" isAnimationActive={false} />
          <Line
            yAxisId="volt"
            dataKey="voltage"
            name="Voltage (V)"
            stroke="#b45309"
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
