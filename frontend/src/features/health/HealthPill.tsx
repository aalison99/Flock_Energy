import { Badge } from "../../shared/ui/Badge";
import type { BadgeTone } from "../../shared/ui/Badge";
import { useReadiness } from "./hooks";

const BREAKER_TONE: Record<string, BadgeTone> = {
  closed: "installed",
  half_open: "faulty",
  open: "danger",
};

/** Header pill: portal circuit-breaker state plus the number of indexed meters. */
export function HealthPill() {
  const { data, isPending, isError } = useReadiness();

  if (isPending) return <Badge>Checking portal…</Badge>;
  if (isError) return <Badge tone="danger">API unreachable</Badge>;

  const { breaker } = data.portal;
  return (
    <div className="flex items-center gap-2" aria-label="Service health">
      <Badge tone={BREAKER_TONE[breaker] ?? "neutral"}>Portal: {breaker.replace("_", " ")}</Badge>
      <Badge tone="neutral">{data.index.meter_count.toLocaleString("en-IN")} meters indexed</Badge>
    </div>
  );
}
