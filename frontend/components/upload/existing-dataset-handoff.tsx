"use client";

/**
 * `/backtest/new?dataset_id=…` — the DATASET_SAVED handoff for a dataset that
 * was already saved, whether by this wizard or picked from `/datasets`.
 *
 * Loading it here (rather than trusting the query string) is what enforces
 * ownership: a dataset id belonging to someone else returns the backend's
 * indistinguishable 404, which reveals nothing about whether it exists.
 */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { DatasetSavedStep } from "@/components/upload/dataset-saved-step";
import { WizardProgress } from "@/components/upload/wizard-progress";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/ui/loading-state";
import { getDataset } from "@/lib/api/datasets";
import type { DatasetDetail } from "@/lib/api/dataset-types";
import { ApiClientError } from "@/lib/api/errors";

export function ExistingDatasetHandoff({ datasetId }: { datasetId: number }) {
  const [detail, setDetail] = useState<DatasetDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const mounted = useRef(true);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      controller.current?.abort();
    };
  }, []);

  // The fetch runs inside the effect, so nothing is set synchronously in its
  // body; retrying bumps this key from an event handler instead.
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const next = new AbortController();
    controller.current = next;
    let cancelled = false;

    void (async () => {
      try {
        const response = await getDataset(datasetId, next.signal);
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
      next.abort();
    };
  }, [datasetId, reloadKey]);

  const retry = useCallback(() => {
    setLoading(true);
    setError(null);
    setDetail(null);
    setReloadKey((key) => key + 1);
  }, []);

  if (loading) return <LoadingState label="Loading dataset…" />;

  if (error !== null || detail === null) {
    return (
      <Alert
        tone="error"
        title="Dataset unavailable"
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
        {error ?? "Dataset not found."}
      </Alert>
    );
  }

  return (
    <>
      <WizardProgress step="DATASET_SAVED" />
      <DatasetSavedStep
        dataset={{
          id: detail.id,
          name: detail.name,
          data_mode: detail.data_mode,
          start_date: detail.start_date,
          end_date: detail.end_date,
          row_count: detail.row_count,
        }}
      />
    </>
  );
}
