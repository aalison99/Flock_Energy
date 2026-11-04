import { useCallback, useEffect } from "react";
import { ApiError } from "../../lib/api-error";
import { Empty } from "../../shared/ui/Empty";
import { ErrorState } from "../../shared/ui/ErrorState";
import { Loading } from "../../shared/ui/Loading";
import { Pagination } from "../../shared/ui/Pagination";
import { useUrlState } from "../../shared/url-state";
import { FilterBar } from "./FilterBar";
import { useMeters } from "./hooks";
import { MeterTable } from "./MeterTable";
import { SearchBox } from "./SearchBox";

export const PAGE_SIZE = 25;

export function MetersExplorer() {
  const [state, update] = useUrlState({ q: "", page: "1" });
  const page = Math.max(1, Number.parseInt(state.page, 10) || 1);
  const { data, error, isPending, isError, isPlaceholderData, refetch } = useMeters({ q: state.q, page, pageSize: PAGE_SIZE });

  const onSearch = useCallback((q: string) => update({ q, page: "1" }, { replace: true }), [update]);

  // A URL like ?page=999 is pulled back to the last real page.
  const totalPages = data?.total_pages;
  useEffect(() => {
    if (totalPages === undefined || isPlaceholderData) return;
    const last = Math.max(totalPages, 1);
    if (page > last) update({ page: String(last) }, { replace: true });
  }, [totalPages, isPlaceholderData, page, update]);

  const indexSyncing = error instanceof ApiError && error.status === 409;

  return (
    <section className="space-y-4">
      <h1 className="text-xl font-semibold">Meters</h1>
      <SearchBox value={state.q} onChange={onSearch} />
      <FilterBar indexReady={!indexSyncing} />

      {indexSyncing ? (
        <div role="status" className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-800">
          <p>The local index is still syncing, so this view isn't available yet.</p>
          <p className="mt-1 text-sky-700">{error.message}</p>
          <button
            type="button"
            onClick={() => void refetch()}
            className="mt-2 rounded border border-sky-300 bg-white px-3 py-1 text-sm hover:bg-sky-100"
          >
            Retry
          </button>
        </div>
      ) : isPending ? (
        <Loading label="Loading meters…" />
      ) : isError ? (
        <ErrorState title="Could not load meters" message={error.message} />
      ) : data.items.length === 0 ? (
        <Empty title="No meters found">
          {state.q ? `Nothing matches “${state.q}”.` : "The index has no meters yet."}
        </Empty>
      ) : (
        <>
          <MeterTable items={data.items} busy={isPlaceholderData} />
          <Pagination
            page={data.page}
            totalPages={data.total_pages}
            total={data.total}
            hasNext={data.has_next}
            onPageChange={(p) => update({ page: String(p) })}
          />
        </>
      )}
    </section>
  );
}
