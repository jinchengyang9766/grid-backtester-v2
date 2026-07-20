"use client";

/**
 * `/backtest/new?dataset_id=…`.
 *
 * Thin wrapper around the strategy flow, which loads the owned dataset itself.
 * `configure=1` skips the saved-dataset handoff and opens the configuration
 * form directly, which is how the upload wizard continues after saving.
 */

import { BacktestFlow } from "@/components/backtests/backtest-flow";

export function ExistingDatasetHandoff({
  datasetId,
  startAtConfiguration = false,
}: {
  datasetId: number;
  startAtConfiguration?: boolean;
}) {
  const initialStep = startAtConfiguration ? "STRATEGY_CONFIG" : "DATASET_SAVED";
  return (
    // Keyed on the dataset so a different one starts from clean state.
    <BacktestFlow
      key={`${datasetId}:${initialStep}`}
      datasetId={datasetId}
      initialStep={initialStep}
    />
  );
}
