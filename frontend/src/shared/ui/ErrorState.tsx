import type { ReactNode } from "react";

export function ErrorState({
  title = "Something went wrong",
  message,
  children,
}: {
  title?: string;
  message?: string;
  children?: ReactNode;
}) {
  return (
    <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      <p className="font-medium">{title}</p>
      {message ? <p className="mt-1">{message}</p> : null}
      {children ? <div className="mt-2">{children}</div> : null}
    </div>
  );
}
