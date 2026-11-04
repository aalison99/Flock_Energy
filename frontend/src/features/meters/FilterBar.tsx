/**
 * Slot for filter chips, facet counts, the DT select and sort (M9b, once the
 * facets API lands). `indexReady` is false on a 409, when chips must stay hidden.
 */
export function FilterBar({ indexReady }: { indexReady: boolean }) {
  if (!indexReady) return null;
  return null;
}
