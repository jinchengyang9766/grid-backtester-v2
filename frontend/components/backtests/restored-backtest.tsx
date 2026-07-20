"use client";

/**
 * `/backtest/new?backtest_id=…` — restore a previously created run.
 *
 * Loading the run by id is what enforces ownership: a foreign or missing id
 * gets the backend's indistinguishable 404. Nothing is re-executed, and no
 * result series is requested — only the same handoff summary the run produced.
 */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { BacktestCompletedStep } from "@/components/backtests/backtest-completed-step";
import { BacktestFailedStep } from "@/components/backtests/backtest-failed-step";
import { WizardProgress } from "@/components/upload/wizard-progress";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/ui/loading-state";
import type { BacktestDetailResponse } from "@/lib/api/backtest-types";
import { getBacktest } from "@/lib/api/backtests";
import { ApiClientError } from "@/lib/api/errors";

export function RestoredBacktest({
  backtestId,
  onRunAnother,
}: {
  backtestId: number;
  /** Navigates back to the configuration form for this run's dataset. */
  onRunAnother: (datasetId: number) => void;
}) {
  const [detail, setDetail] = useState<BacktestDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    void (async () => {
      try {
        // No `include`: the trades/equity series stay out of this response.
        const response = await getBacktest(backtestId, { signal: controller.signal });
        if (cancelled || !mounted.current) return;
        setDetail(response);
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        if (cancelled || !mounted.current) return;
        setError(
          caught instanceof ApiClientError
            ? caught.message
            : "Something went wrong. Please try again.",
        );
      } finally {
        if (!cancelled && mounted.current) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [backtestId, reloadKey]);

  const retry = useCallback(() => {
    setLoading(true);
    setError(null);
    setDetail(null);
    setReloadKey((key) => key + 1);
  }, []);

  if (loading) return <LoadingState label="Loading backtest…" />;

  if (error !== null || detail === null) {
    return (
      <Alert
        tone="error"
        title="Backtest unavailable"
        action={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={retry}>
              Try again
            </Button>
            <Link
              href="/datasets"
              className="inline-flex items-center justify-center rounded-md border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-800 transition-colors hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
            >
              Back to datasets
            </Link>
          </div>
        }
      >
        {error ?? "Backtest not found."}
      </Alert>
    );
  }

  const summary = {
    id: detail.id,
    name: detail.name,
    status: detail.status,
    created_at: detail.created_at,
    completed_at: detail.completed_at,
  };

  return (
    <>
      <WizardProgress step="DONE" />
      {detail.status === "FAILED" ? (
        <BacktestFailedStep
          run={{ ...summary, error_message: detail.error_message }}
          datasetName={detail.dataset.name}
          onEditConfiguration={() => onRunAnother(detail.dataset_id)}
        />
      ) : (
        <BacktestCompletedStep
          run={{ ...summary, result_metrics: detail.result_metrics }}
          datasetName={detail.dataset.name}
          onRunAnother={() => onRunAnother(detail.dataset_id)}
        />
      )}
    </>
  );
}
