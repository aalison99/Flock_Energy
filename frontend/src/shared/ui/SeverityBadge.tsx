import { Badge } from "./Badge";
import type { BadgeTone } from "./Badge";

export type Severity = "info" | "warning" | "error";

const TONE: Record<Severity, BadgeTone> = { error: "danger", warning: "faulty", info: "neutral" };

/** error = red, warning = amber, info = slate. */
export function SeverityBadge({ severity }: { severity: Severity }) {
  return <Badge tone={TONE[severity]}>{severity}</Badge>;
}
