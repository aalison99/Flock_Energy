import { lazy, Suspense } from "react";
import { ApiError } from "../../lib/api-error";
import { Empty } from "../../shared/ui/Empty";
import { ErrorState } from "../../shared/ui/ErrorState";
import { Loading } from "../../shared/ui/Loading";
import { useUrlState } from "../../shared/url-state";
import { toChartPoints } from "./chart-data";
import { useReadings } from "./hooks";
import { ResolutionToggle } from "./ResolutionToggle";
import { SummaryTiles } from "./SummaryTiles";
import { RESOLUTIONS } from "./types";
import type { Resolution } from "./types";

// Recharts is heavy; load it only when a meter page is opened.
const ReadingsChart = lazy(() => import("./ReadingsChart"));

const DEFAULT_RESOLUTION: Resolution = "daily";

function parseResolution(value: string): Resolution {
  return (RESOLUTIONS as string[]).includes(value) ? (value as Resolution) : DEFAULT_RESOLUTION;
}

export function ReadingsPanel({ meterId }: { meterId: string }) {
  const [state, update] = useUrlState({ res: DEFAULT_RESOLUTION as string });
  const resolution = parseResolution(state.res);
  const { data, error, isPending, isError } = useReadings(meterId, resolution);
  const points = data ? toChartPoints(data) : [];

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Readings</h2>
        <ResolutionToggle value={resolution} onChange={(res) => update({ res })} />
      </div>

      {isPending ? (
        <Loading label="Loading readings…" />
      ) : isError ? (
        <ErrorState title="Could not load readings" message={error.message}>
          {error instanceof ApiError && error.status === 422 && resolution !== "daily" ? (
            <button
              type="button"
              className="rounded border border-red-300 bg-white px-3 py-1 text-sm hover:bg-red-100"
              onClick={() => update({ res: "daily" })}
            >
              Show daily
            </button>
          ) : null}
        </ErrorState>
      ) : (
        <>
          <SummaryTiles series={data} />
          {points.length === 0 ? (
            <Empty title="No readings in this range" />
          ) : (
            <Suspense fallback={<Loading label="Loading chart…" />}>
              <ReadingsChart data={points} resolution={resolution} />
            </Suspense>
          )}
        </>
      )}
    </section>
  );
}
