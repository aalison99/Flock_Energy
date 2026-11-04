import { formatDateTime } from "../../shared/format";
import { Badge } from "../../shared/ui/Badge";
import type { MeterDetail } from "./types";

export function Freshness({ meta }: { meta: MeterDetail["meta"] }) {
  return (
    <p className="flex items-center gap-2 text-xs text-slate-500">
      <span>
        Source: {meta.source} · fetched {formatDateTime(meta.fetched_at)}
      </span>
      {meta.stale ? <Badge tone="faulty">stale</Badge> : null}
    </p>
  );
}
