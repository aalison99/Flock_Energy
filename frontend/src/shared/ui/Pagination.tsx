interface Props {
  page: number;
  totalPages: number;
  total: number;
  hasNext: boolean;
  onPageChange: (page: number) => void;
}

export function Pagination({ page, totalPages, total, hasNext, onPageChange }: Props) {
  const btn =
    "rounded border border-slate-300 bg-white px-3 py-1 text-sm disabled:cursor-not-allowed disabled:opacity-40";
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between py-3 text-sm text-slate-600">
      <span>
        {total.toLocaleString("en-IN")} results · page {page} of {Math.max(totalPages, 1)}
      </span>
      <div className="flex gap-2">
        <button type="button" className={btn} disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          Previous
        </button>
        <button type="button" className={btn} disabled={!hasNext} onClick={() => onPageChange(page + 1)}>
          Next
        </button>
      </div>
    </nav>
  );
}
