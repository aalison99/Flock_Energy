import type { ReactNode } from "react";

/** Shown when the API answers 409: the local index is empty or still syncing. */
export function IndexSyncingNotice({ message, children }: { message?: string; children?: ReactNode }) {
  return (
    <div role="status" className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-800">
      <p className="font-medium">The index is empty — start a sync</p>
      <p className="mt-1">This view needs the local index, which has no meters yet.</p>
      {message ? <p className="mt-1 text-sky-700">{message}</p> : null}
      {children ? <div className="mt-2">{children}</div> : null}
    </div>
  );
}
