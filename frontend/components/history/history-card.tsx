"use client";

import Link from "next/link";

import { ResultStatus } from "@/components/results/result-status";
import { Button } from "@/components/ui/button";
import type { BacktestListItem } from "@/lib/api/backtest-history-types";
import { headlineRows } from "@/lib/backtests/metrics";
import { metricText } from "@/components/results/metric-grid";
import { dateRangeLabel, displayText, timestampLabel } from "@/lib/datasets/display";

export interface HistoryCardProps {
  run: BacktestListItem;
  selected: boolean;
  busy: boolean;
  onToggleSelected: (run: BacktestListItem) => void;
  onRename: (run: BacktestListItem) => void;
  onRerun: (run: BacktestListItem) => void;
  onDuplicate: (run: BacktestListItem) => void;
  onDelete: (run: BacktestListItem) => void;
}

export function HistoryCard({
  run,
  selected,
  busy,
  onToggleSelected,
  onRename,
  onRerun,
  onDuplicate,
  onDelete,
}: HistoryCardProps) {
  // Only figures already stored on the list row are shown; a FAILED or
  // pending run simply has none.
  const summary = headlineRows(run.result_metrics)
    .filter((row) => row.value !== null)
    .slice(0, 3);

  return (
    <li className="rounded-md border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <input
            type="checkbox"
            checked={selected}
            disabled={busy}
            onChange={() => onToggleSelected(run)}
            aria-label={`Select ${run.name} for comparison`}
            className="mt-1 size-4 rounded border-slate-400 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
          />
          <div>
            <h3 className="text-base font-semibold break-words">
              <Link
                href={`/history/${run.id}`}
                className="text-sky-800 underline underline-offset-2 hover:text-sky-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:text-sky-300"
              >
                {run.name}
              </Link>
            </h3>
            <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-400">
              ID {run.id} · {run.dataset_name}
            </p>
          </div>
        </div>
        <ResultStatus status={run.status} />
      </div>

      <dl className="mt-3 grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
        {(
          [
            ["Backtest range", dateRangeLabel(run.start_date, run.end_date)],
            ["Path mode", displayText(run.ohlc_path_mode)],
            ["Created", timestampLabel(run.created_at)],
            ["Completed", run.completed_at ? timestampLabel(run.completed_at) : "—"],
            ...summary.map((row): [string, string] => [row.label, metricText(row)]),
          ] as [string, string][]
        ).map(([label, value]) => (
          <div key={label} className="flex justify-between gap-3">
            <dt className="text-slate-600 dark:text-slate-400">{label}</dt>
            <dd className="text-right font-medium break-words">{value}</dd>
          </div>
        ))}
      </dl>

      {run.error_message !== null && (
        <p className="mt-2 rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
          {run.error_message}
        </p>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <Link
          href={`/history/${run.id}`}
          aria-label={`View results for ${run.name}`}
          className="inline-flex items-center justify-center rounded-md bg-sky-700 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-sky-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
        >
          View results
        </Link>
        <Button
          variant="secondary"
          disabled={busy}
          onClick={() => onRename(run)}
          aria-label={`Rename ${run.name}`}
        >
          Rename
        </Button>
        <Button
          variant="secondary"
          disabled={busy}
          onClick={() => onRerun(run)}
          aria-label={`Rerun ${run.name}`}
        >
          Rerun
        </Button>
        <Button
          variant="secondary"
          disabled={busy}
          onClick={() => onDuplicate(run)}
          aria-label={`Duplicate ${run.name}`}
        >
          Duplicate
        </Button>
        <Button
          variant="destructive"
          disabled={busy}
          onClick={() => onDelete(run)}
          aria-label={`Delete ${run.name}`}
        >
          Delete
        </Button>
      </div>
    </li>
  );
}
