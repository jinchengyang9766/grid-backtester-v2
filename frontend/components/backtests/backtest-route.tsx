"use client";

/**
 * Chooses what `/backtest/new` shows, from the query string alone:
 *
 *   ?backtest_id=…  restore a created run's handoff
 *   ?dataset_id=…   configure and run against a saved dataset
 *   (neither)       the upload wizard, starting at UPLOAD
 *
 * `backtest_id` wins when both are present, because a created run is the more
 * specific thing to show. Only ids ever appear in the URL — never a preview
 * token, a configuration, or any result metric.
 */

import { useRouter } from "next/navigation";

import { BacktestFlow } from "@/components/backtests/backtest-flow";
import { RestoredBacktest } from "@/components/backtests/restored-backtest";
import { DatasetUploadWizard } from "@/components/upload/dataset-upload-wizard";

export function BacktestRoute({
  datasetId,
  backtestId,
  startAtConfiguration,
}: {
  datasetId: number | null;
  backtestId: number | null;
  startAtConfiguration: boolean;
}) {
  const router = useRouter();

  if (backtestId !== null) {
    return (
      <RestoredBacktest
        backtestId={backtestId}
        onRunAnother={(runDatasetId) =>
          router.replace(`/backtest/new?dataset_id=${runDatasetId}&configure=1`)
        }
      />
    );
  }

  if (datasetId !== null) {
    const initialStep = startAtConfiguration ? "STRATEGY_CONFIG" : "DATASET_SAVED";
    return (
      // Keyed on the dataset: selecting a different one mounts a fresh flow,
      // so strategy state never carries across datasets.
      <BacktestFlow
        key={`${datasetId}:${initialStep}`}
        datasetId={datasetId}
        initialStep={initialStep}
      />
    );
  }

  return <DatasetUploadWizard />;
}
