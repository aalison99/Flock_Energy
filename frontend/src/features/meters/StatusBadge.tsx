import { Badge } from "../../shared/ui/Badge";
import type { MeterSummary } from "./types";

export function StatusBadge({ status }: { status: MeterSummary["install_status"] }) {
  const tone = status === "unknown" ? "neutral" : status;
  return <Badge tone={tone}>{status}</Badge>;
}
