"use client";

import Link from "next/link";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { statusLabel } from "@/lib/backtests/display";
import { timestampLabel } from "@/lib/datasets/display";

export interface FailedRun {
  id: number;
  name: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  error_message: string | null;
}

/**
 * DONE, for a FAILED run.
 *
 * A 201 with `status: "FAILED"` is a *created* run, not a request failure: the
 * row exists and is saved. No metrics are shown because none were produced,
 * and none are invented.
 */
export function BacktestFailedStep({
  run,
  datasetName,
  onEditConfiguration,
}: {
  run: FailedRun;
  datasetName: string;
  onEditConfiguration: () => void;
}) {
  return (
    <section aria-labelledby="failed-heading" className="space-y-5">
      <Alert tone="error" title="Backtest did not complete">
        <p className="break-words">
          <span className="font-medium">{run.name}</span> was saved, but the
          engine stopped before producing a result.
        </p>
      </Alert>

      <div>
        <h2 id="failed-heading" className="text-lg font-semibold">
          Run summary
        </h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          The run record was created and kept, so you can see exactly what was
          attempted.
        </p>
      </div>

      <dl className="grid gap-x-6 gap-y-2 rounded-md border border-slate-200 p-3 text-sm sm:grid-cols-2 dark:border-slate-700">
        {(
          [
            ["Backtest ID", String(run.id)],
            ["Name", run.name],
            ["Status", statusLabel(run.status)],
            ["Dataset", datasetName],
            ["Created", timestampLabel(run.created_at)],
            ["Completed", run.completed_at ? timestampLabel(run.completed_at) : "—"],
          ] as [string, string][]
        ).map(([label, value]) => (
          <div key={label} className="flex justify-between gap-3">
            <dt className="text-slate-600 dark:text-slate-400">{label}</dt>
            <dd className="text-right font-medium break-words">{value}</dd>
          </div>
        ))}
      </dl>

      <div>
        <h3 className="text-sm font-semibold">Reported reason</h3>
        <p className="mt-2 rounded-md border border-slate-200 p-3 text-sm break-words dark:border-slate-700">
          {run.error_message ?? "No reason was recorded for this run."}
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button onClick={onEditConfiguration}>Edit configuration</Button>
        <Button variant="secondary" onClick={onEditConfiguration}>
          Start another run
        </Button>
        <Link
          href="/datasets"
          className="inline-flex items-center justify-center rounded-md px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          Return to datasets
        </Link>
      </div>
      <p className="text-xs text-slate-600 dark:text-slate-400">
        Editing returns you to the form with the settings you submitted. Nothing
        is resubmitted automatically.
      </p>
    </section>
  );
}
