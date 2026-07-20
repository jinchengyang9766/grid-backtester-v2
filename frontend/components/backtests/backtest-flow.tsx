"use client";

/**
 * The strategy half of the wizard: DATASET_SAVED → STRATEGY_CONFIG → RUNNING
 * → DONE (SPEC Section 28).
 *
 * It needs only a dataset id. The original File and the preview token are
 * irrelevant from here on, which is what lets `?dataset_id=` resume after a
 * reload. Strategy state is held in component memory and tied to the loaded
 * dataset: selecting a different dataset resets it rather than carrying
 * settings across securities.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { BacktestCompletedStep } from "@/components/backtests/backtest-completed-step";
import { BacktestFailedStep } from "@/components/backtests/backtest-failed-step";
import { RunningStep } from "@/components/backtests/running-step";
import { StrategyConfigStep } from "@/components/backtests/strategy-config-step";
import { DatasetSavedStep } from "@/components/upload/dataset-saved-step";
import { WizardProgress } from "@/components/upload/wizard-progress";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/ui/loading-state";
import type { BacktestCreateResponse } from "@/lib/api/backtest-types";
import { isConfigurationErrorCode } from "@/lib/api/backtest-types";
import { createBacktest } from "@/lib/api/backtests";
import type { DatasetDetail } from "@/lib/api/dataset-types";
import { getDataset } from "@/lib/api/datasets";
import { ApiClientError } from "@/lib/api/errors";
import {
  cloneConfiguration,
  serializeConfiguration,
  type ConfigurationFormState,
} from "@/lib/backtests/configuration-state";
import {
  backendFieldError,
  isGridSectionCode,
  validateConfiguration,
  type FieldErrors,
} from "@/lib/backtests/configuration-validation";
import { defaultConfiguration } from "@/lib/backtests/defaults";
import type { WizardStep } from "@/lib/datasets/wizard-state";
import Link from "next/link";

const GENERIC_FAILURE = "Something went wrong. Please try again.";

function messageOf(error: unknown): string {
  return error instanceof ApiClientError ? error.message : GENERIC_FAILURE;
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export interface BacktestFlowProps {
  datasetId: number;
  /** Start on the saved-dataset handoff, or go straight to the form. */
  initialStep?: Extract<WizardStep, "DATASET_SAVED" | "STRATEGY_CONFIG">;
}

export function BacktestFlow({
  datasetId,
  initialStep = "DATASET_SAVED",
}: BacktestFlowProps) {
  const router = useRouter();

  const [dataset, setDataset] = useState<DatasetDetail | null>(null);
  const [datasetError, setDatasetError] = useState<string | null>(null);
  const [datasetLoading, setDatasetLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  const [step, setStep] = useState<WizardStep>(initialStep);
  const [configuration, setConfiguration] = useState<ConfigurationFormState>(
    defaultConfiguration,
  );
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [gridError, setGridError] = useState<string | null>(null);
  const [datasetMissing, setDatasetMissing] = useState(false);
  const [run, setRun] = useState<BacktestCreateResponse | null>(null);

  const mounted = useRef(true);
  const runController = useRef<AbortController | null>(null);
  // Only the newest run may publish, so a response for a previous dataset can
  // never be attached to the current one.
  const runGeneration = useRef(0);
  const running = step === "RUNNING";

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      runController.current?.abort();
    };
  }, []);

  // Loading a different dataset discards everything derived from the old one.
  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    void (async () => {
      try {
        const detail = await getDataset(datasetId, controller.signal);
        if (cancelled || !mounted.current) return;
        setDataset(detail);
      } catch (error) {
        if (isAbort(error) || cancelled || !mounted.current) return;
        setDatasetError(messageOf(error));
      } finally {
        if (!cancelled && mounted.current) setDatasetLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [datasetId, reloadKey]);

  // Strategy state belongs to one dataset. Callers mount this component with
  // a key derived from the dataset id, so a different dataset produces a
  // fresh instance rather than settings leaking across securities.

  const retryDataset = useCallback(() => {
    setDatasetLoading(true);
    setDatasetError(null);
    setDataset(null);
    setReloadKey((key) => key + 1);
  }, []);

  const handleSubmit = useCallback(async () => {
    if (running || dataset === null) return;

    const validation = validateConfiguration(configuration);
    if (!validation.valid) {
      setFieldErrors(validation.fieldErrors);
      setFormError("Fix the highlighted fields before running.");
      setGridError(null);
      return;
    }

    setFieldErrors({});
    setFormError(null);
    setGridError(null);
    setDatasetMissing(false);
    setStep("RUNNING");

    runController.current?.abort();
    const controller = new AbortController();
    runController.current = controller;
    const generation = ++runGeneration.current;

    try {
      const response = await createBacktest(
        {
          dataset_id: dataset.id,
          configuration: serializeConfiguration(configuration, dataset.data_mode),
        },
        controller.signal,
      );
      if (!mounted.current || generation !== runGeneration.current) return;
      // A FAILED status here is still a created run, not a request error.
      setRun(response);
      setStep("DONE");
      // Only the id goes in the URL — never the configuration or metrics.
      router.replace(`/backtest/new?backtest_id=${response.id}`);
    } catch (error) {
      if (isAbort(error)) return;
      if (!mounted.current || generation !== runGeneration.current) return;

      // A non-2xx never produced a run: stay on the form with values intact.
      setStep("STRATEGY_CONFIG");
      if (error instanceof ApiClientError) {
        setFormError(error.message);
        if (error.code === "DATASET_NOT_FOUND") {
          setDatasetMissing(true);
        } else if (isConfigurationErrorCode(error.code)) {
          const hint = backendFieldError(error.details);
          if (hint !== null) {
            setFieldErrors({ [hint.path]: error.message });
          }
          if (isGridSectionCode(error.code)) setGridError(error.message);
        }
      } else {
        setFormError(GENERIC_FAILURE);
      }
    }
  }, [configuration, dataset, router, running]);

  if (datasetLoading) return <LoadingState label="Loading dataset…" />;

  if (datasetError !== null || dataset === null) {
    return (
      <Alert
        tone="error"
        title="Dataset unavailable"
        action={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={retryDataset}>
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
        {datasetError ?? "Dataset not found."}
      </Alert>
    );
  }

  return (
    <>
      <WizardProgress step={step} />

      {step === "DATASET_SAVED" && (
        <DatasetSavedStep
          dataset={{
            id: dataset.id,
            name: dataset.name,
            data_mode: dataset.data_mode,
            start_date: dataset.start_date,
            end_date: dataset.end_date,
            row_count: dataset.row_count,
          }}
          onConfigureStrategy={() => setStep("STRATEGY_CONFIG")}
        />
      )}

      {step === "STRATEGY_CONFIG" && (
        <StrategyConfigStep
          dataset={dataset}
          configuration={configuration}
          errors={fieldErrors}
          formError={formError}
          gridError={gridError}
          datasetMissing={datasetMissing}
          pending={false}
          onChange={setConfiguration}
          onReset={() => {
            // Resetting the form never changes the selected dataset.
            setConfiguration(defaultConfiguration());
            setFieldErrors({});
            setFormError(null);
            setGridError(null);
          }}
          onSubmit={() => void handleSubmit()}
        />
      )}

      {step === "RUNNING" && <RunningStep dataset={dataset} />}

      {step === "DONE" && run !== null && run.status === "FAILED" && (
        <BacktestFailedStep
          run={run}
          datasetName={dataset.name}
          onEditConfiguration={() => {
            // The submitted values are still in state, ready to correct.
            setStep("STRATEGY_CONFIG");
            router.replace(`/backtest/new?dataset_id=${dataset.id}`);
          }}
        />
      )}

      {step === "DONE" && run !== null && run.status !== "FAILED" && (
        <BacktestCompletedStep
          run={run}
          datasetName={dataset.name}
          onRunAnother={() => {
            // Keep the dataset and the settings; just go back to the form.
            setStep("STRATEGY_CONFIG");
            setRun(null);
            router.replace(`/backtest/new?dataset_id=${dataset.id}`);
          }}
        />
      )}
    </>
  );
}

/** Keep the previously-submitted configuration usable after a FAILED run. */
export function copyConfiguration(state: ConfigurationFormState): ConfigurationFormState {
  return cloneConfiguration(state);
}
