import { lazy, Suspense } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { ApiError } from "../../lib/api-error";
import { Empty } from "../../shared/ui/Empty";
import { ErrorState } from "../../shared/ui/ErrorState";
import { Loading } from "../../shared/ui/Loading";
import { Breadcrumb } from "./Breadcrumb";
import { Freshness } from "./Freshness";
import { useMeter } from "./hooks";
import { MeterAnomalies } from "./MeterAnomalies";
import { NameplateCard } from "./NameplateCard";

const MiniMap = lazy(() => import("./MiniMap"));

/** Meter header (nameplate, breadcrumb, freshness, map). `children` render only once the meter exists. */
export function MeterDetailView({ meterId, children }: { meterId: string; children?: ReactNode }) {
  const { data: meter, error, isPending, isError } = useMeter(meterId);

  if (isPending) return <Loading label="Loading meter…" />;
  if (isError) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <Empty title="Meter not found">
          <p>No meter with id {meterId}.</p>
          <Link className="mt-2 inline-block text-sky-700 hover:underline" to="/meters">
            Back to meters
          </Link>
        </Empty>
      );
    }
    return <ErrorState title="Could not load meter" message={error.message} />;
  }

  return (
    <div className="space-y-4">
      <Link className="text-sm text-sky-700 hover:underline" to="/meters">
        ← All meters
      </Link>
      <Breadcrumb hierarchy={meter.hierarchy} />
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <NameplateCard meter={meter} />
          <Freshness meta={meter.meta} />
        </div>
        {meter.geo ? (
          <Suspense fallback={<Loading label="Loading map…" />}>
            <MiniMap lat={meter.geo.lat} lng={meter.geo.lng} />
          </Suspense>
        ) : null}
      </div>
      <MeterAnomalies meterId={meterId} />
      {children}
    </div>
  );
}
