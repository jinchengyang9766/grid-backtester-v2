import type { ReactNode } from "react";

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  /** What the user should do next — an empty state always offers a way on. */
  action?: ReactNode;
}) {
  return (
    <div className="rounded-md border border-dashed border-slate-300 px-6 py-10 text-center dark:border-slate-700">
      <p className="text-sm font-medium text-slate-800 dark:text-slate-100">{title}</p>
      <div className="mx-auto mt-1 max-w-prose text-sm text-slate-600 dark:text-slate-400">
        {children}
      </div>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}
