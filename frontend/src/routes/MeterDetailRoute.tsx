import { useParams } from "react-router";
import { MeterDetailView } from "../features/meters";
import { ReadingsPanel } from "../features/readings";

export function MeterDetailRoute() {
  const { meterId = "" } = useParams();
  return (
    <MeterDetailView meterId={meterId}>
      <ReadingsPanel meterId={meterId} />
    </MeterDetailView>
  );
}
