import { Badge } from "../../shared/ui/Badge";
import type { BadgeTone } from "../../shared/ui/Badge";
import { useReadiness } from "./hooks";

const BREAKER: Record<string, { tone: BadgeTone; text: string }> = {
  closed: { tone: "installed", text: "Portal OK" },
  half_open: { tone: "faulty", text: "Portal recovering" },
  open: { tone: "danger", text: "Portal unavailable" },
};

/** Header pill: portal circuit-breaker state plus the number of indexed meters. */
export function HealthPill() {
  const { data, isPending, isError } = useReadiness();

  if (isPending) return <Badge>Checking portal…</Badge>;
  if (isError) return <Badge tone="danger">API unreachable</Badge>;

  const breaker = BREAKER[data.portal.breaker] ?? { tone: "neutral" as const, text: `Portal: ${data.portal.breaker}` };
  const { index } = data;
  return (
    <div className="flex items-center gap-2" role="status">
      <Badge tone={breaker.tone}>{breaker.text}</Badge>
      <Badge tone="neutral">
        {index.ready ? `${index.meter_count.toLocaleString("en-IN")} meters indexed` : "Index syncing…"}
      </Badge>
    </div>
  );
}
