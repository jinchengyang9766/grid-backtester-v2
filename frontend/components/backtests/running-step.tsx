"use client";

import type { DatasetDetail } from "@/lib/api/dataset-types";

/**
 * RUNNING (SPEC Section 28).
 *
 * Execution is synchronous, so the browser is simply waiting on one HTTP
 * response. There is no progress channel and therefore no percentage — a
 * fabricated bar would imply information the server never sent. There is also
 * no Cancel, because the backend exposes no cancellation for a backtest.
 */
export function RunningStep({ dataset }: { dataset: DatasetDetail }) {
  return (
    <section
      aria-labelledby="running-heading"
      className="rounded-md border border-slate-200 p-6 dark:border-slate-700"
    >
      <div role="status" aria-live="polite" className="flex items-start gap-3">
        <span
          aria-hidden="true"
          className="mt-1 size-5 shrink-0 animate-spin rounded-full border-2 border-sky-700 border-t-transparent motion-reduce:animate-none"
        />
        <div>
          <h2 id="running-heading" className="text-lg font-semibold">
            Running backtest…
          </h2>
          <p className="mt-1 text-sm text-slate-700 dark:text-slate-300">
            The server is running the strategy over{" "}
            <span className="font-medium break-words">{dataset.name}</span> (
            {dataset.row_count} rows). This happens in a single request, so the
            page waits here until the result comes back.
          </p>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
            Please keep this tab open. Editing is disabled while the run is in
            progress.
          </p>
        </div>
      </div>
    </section>
  );
}
