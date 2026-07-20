"use client";

import Link from "next/link";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { headlineMetrics, statusLabel } from "@/lib/backtests/display";
import { timestampLabel } from "@/lib/datasets/display";

export interface CompletedRun {
  id: number;
  name: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  result_metrics: Record<string, unknown> | null;
}

/**
 * DONE, for a COMPLETED run.
 *
 * Shows only what the response already contained. No result series is
 * fetched, nothing is charted, and no metric is derived — the full dashboard
 * is a later task.
 */
export function BacktestCompletedStep({
  run,
  datasetName,
  onRunAnother,
}: {
  run: CompletedRun;
  datasetName: string;
  onRunAnother: () => void;
}) {
  const metrics = headlineMetrics(run.result_metrics);

  return (
    <section aria-labelledby="completed-heading" className="space-y-5">
      <Alert tone="success" title="Backtest completed">
        <p className="break-words">
          <span className="font-medium">{run.name}</span> finished successfully.
        </p>
      </Alert>

      <div>
        <h2 id="completed-heading" className="text-lg font-semibold">
          Run summary
        </h2>
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

      {metrics.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold">Stored headline figures</h3>
          <dl className="mt-2 grid gap-x-6 gap-y-2 rounded-md border border-slate-200 p-3 text-sm sm:grid-cols-2 dark:border-slate-700">
            {metrics.map((metric) => (
              <div key={metric.label} className="flex justify-between gap-3">
                <dt className="text-slate-600 dark:text-slate-400">{metric.label}</dt>
                <dd className="text-right font-medium tabular-nums break-words">
                  {metric.value}
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-xs text-slate-600 dark:text-slate-400">
            These values are taken directly from the saved result. Nothing is
            recalculated here.
          </p>
        </div>
      )}

      <Alert tone="info">
        The full result dashboard — metrics, equity and drawdown charts, the
        trade table, and saved history — arrives in the next step of the build.
      </Alert>

      <div className="flex flex-wrap gap-2">
        <Button onClick={onRunAnother}>Run another backtest</Button>
        <Link
          href="/datasets"
          className="inline-flex items-center justify-center rounded-md border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-800 transition-colors hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
        >
          Return to datasets
        </Link>
      </div>
      <p className="text-xs text-slate-600 dark:text-slate-400">
        &ldquo;Run another backtest&rdquo; keeps this dataset selected and returns
        you to the configuration form with your settings intact.
      </p>
    </section>
  );
}
