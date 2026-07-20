"use client";

import Link from "next/link";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { dataModeLabel, dateRangeLabel } from "@/lib/datasets/display";
import type { SavedDatasetHandoff } from "@/lib/datasets/wizard-state";

/**
 * DATASET_SAVED (SPEC Section 28).
 *
 * The handoff Task 22 continues from. Strategy configuration is deliberately
 * not built here — the control below is inert and labelled as such rather
 * than being a form that cannot yet do anything.
 */
export function DatasetSavedStep({ dataset }: { dataset: SavedDatasetHandoff }) {
  const rows: [string, string][] = [
    ["Dataset ID", String(dataset.id)],
    ["Data mode", dataModeLabel(dataset.data_mode)],
    ["Date range", dateRangeLabel(dataset.start_date, dataset.end_date)],
    ["Rows saved", String(dataset.row_count)],
  ];

  return (
    <section aria-labelledby="saved-heading" className="space-y-5">
      <Alert tone="success" title="Dataset saved">
        <p className="break-words">
          <span className="font-medium">{dataset.name}</span> is ready to use.
        </p>
      </Alert>

      <div>
        <h2 id="saved-heading" className="text-lg font-semibold">
          Next step: configure the strategy
        </h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          Strategy configuration and backtest execution are not implemented
          yet. This dataset is saved and will be available when they are.
        </p>
      </div>

      <dl className="grid gap-x-6 gap-y-2 rounded-md border border-slate-200 p-3 text-sm sm:grid-cols-2 dark:border-slate-700">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-3">
            <dt className="text-slate-600 dark:text-slate-400">{label}</dt>
            <dd className="font-medium tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>

      <div className="flex flex-wrap items-center gap-3">
        <Button disabled title="Strategy configuration is not implemented yet">
          Configure strategy
        </Button>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          Coming next
        </span>
      </div>

      <div className="flex flex-wrap gap-4 text-sm">
        <Link
          href="/datasets"
          className="font-medium text-sky-700 underline underline-offset-2 hover:text-sky-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:text-sky-400"
        >
          View all datasets
        </Link>
        <Link
          href="/backtest/new"
          className="font-medium text-sky-700 underline underline-offset-2 hover:text-sky-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:text-sky-400"
        >
          Upload another file
        </Link>
      </div>
    </section>
  );
}
