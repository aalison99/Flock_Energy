import { useCallback, useEffect } from "react";
import { Link } from "react-router";
import { ApiError } from "../../lib/api-error";
import { Empty } from "../../shared/ui/Empty";
import { ErrorState } from "../../shared/ui/ErrorState";
import { Loading } from "../../shared/ui/Loading";
import { Pagination } from "../../shared/ui/Pagination";
import { filtersToSearch, hasActiveFilters, useMeterFilters } from "../../shared";
import { FilterBar } from "./FilterBar";
import { useMeters } from "./hooks";
import { MeterTable } from "./MeterTable";
import { SearchBox } from "./SearchBox";

export const PAGE_SIZE = 25;

export function MetersExplorer() {
  const { filters, page, setFilters, setPage, clearFilters } = useMeterFilters();
  const { data, error, isPending, isError, isPlaceholderData, refetch } = useMeters({ filters, page, pageSize: PAGE_SIZE });

  const onSearch = useCallback((q: string) => setFilters({ q }, { replace: true }), [setFilters]);
  const onFilterChange = useCallback((patch: Partial<typeof filters>) => setFilters(patch), [setFilters]);

  // A URL like ?page=999 is pulled back to the last real page.
  const totalPages = data?.total_pages;
  useEffect(() => {
    if (totalPages === undefined || isPlaceholderData) return;
    const last = Math.max(totalPages, 1);
    if (page > last) setPage(last, { replace: true });
  }, [totalPages, isPlaceholderData, page, setPage]);

  const indexSyncing = error instanceof ApiError && error.status === 409;

  return (
    <section className="space-y-4">
      <h1 className="text-xl font-semibold">Meters</h1>
      <SearchBox value={filters.q} onChange={onSearch} />
      {indexSyncing ? null : <FilterBar filters={filters} onChange={onFilterChange} onClear={clearFilters} />}

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
          {hasActiveFilters(filters) ? (
            <button
              type="button"
              onClick={clearFilters}
              className="ml-2 mt-2 rounded border border-sky-300 bg-white px-3 py-1 text-sm hover:bg-sky-100"
            >
              Clear filters
            </button>
          ) : null}
        </div>
      ) : isPending ? (
        <Loading label="Loading meters…" />
      ) : isError ? (
        <ErrorState title="Could not load meters" message={error.message} />
      ) : data.items.length === 0 ? (
        <Empty title="No meters found">
          {filters.q || hasActiveFilters(filters) ? "Nothing matches the current search and filters." : "The index has no meters yet."}
        </Empty>
      ) : (
        <>
          <div className="flex items-center justify-between text-sm text-slate-600">
            <p>
              {data.total.toLocaleString("en-IN")} {data.total === 1 ? "meter" : "meters"}
            </p>
            <Link className="text-sky-700 hover:underline" to={{ pathname: "/map", search: filtersToSearch(filters) }}>
              View on map
            </Link>
          </div>
          <MeterTable items={data.items} busy={isPlaceholderData} />
          <Pagination
            page={data.page}
            totalPages={data.total_pages}
            total={data.total}
            hasNext={data.has_next}
            onPageChange={(p) => setPage(p)}
          />
        </>
      )}
    </section>
  );
}
