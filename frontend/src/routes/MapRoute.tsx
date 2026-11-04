import { Suspense } from "react";
import { MeterMap } from "../features/map";
import { Loading } from "../shared";

export function MapRoute() {
  return (
    <Suspense fallback={<Loading label="Loading map…" />}>
      <MeterMap />
    </Suspense>
  );
}
