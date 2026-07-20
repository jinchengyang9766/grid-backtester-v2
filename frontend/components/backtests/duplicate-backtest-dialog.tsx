"use client";

/**
 * Duplicate and execute.
 *
 * The form starts from the source run's canonical configuration and every
 * field is editable. The whole edited configuration is submitted as
 * `configuration_overrides`: the backend's override schema accepts all
 * fields and validates the merged document through the same full
 * configuration model, so computing a minimal diff would add risk without
 * changing the outcome.
 *
 * The source dataset is fixed — duplicate re-runs the same data with
 * different settings — and the source run is never modified.
 */

import { useState } from "react";

import { StrategyConfigStep } from "@/components/backtests/strategy-config-step";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import type { StrategyDatasetSummary } from "@/lib/backtests/configuration-state";
import type { ConfigurationFormState } from "@/lib/backtests/configuration-state";
import type { FieldErrors } from "@/lib/backtests/configuration-validation";

/** Ties the footer's submit button to the form inside the scrolling body. */
const FORM_ID = "duplicate-strategy-form";

export interface DuplicateDialogProps {
  open: boolean;
  sourceName: string;
  dataset: StrategyDatasetSummary;
  configuration: ConfigurationFormState;
  errors: FieldErrors;
  formError: string | null;
  gridError: string | null;
  pending: boolean;
  onChange: (configuration: ConfigurationFormState) => void;
  onReset: () => void;
  onCancel: () => void;
  onSubmit: () => void;
}

export function DuplicateBacktestDialog({
  open,
  sourceName,
  dataset,
  configuration,
  errors,
  formError,
  gridError,
  pending,
  onChange,
  onReset,
  onCancel,
  onSubmit,
}: DuplicateDialogProps) {
  if (!open) return null;

  return (
    <Dialog
      open
      title="Duplicate and run"
      description={`Starts from "${sourceName}" settings and runs a new backtest on the same dataset.`}
      onClose={pending ? () => undefined : onCancel}
      dismissOnBackdrop={false}
      footer={
        <>
          {/* The strategy form is long enough to scroll, so its submit button
              lives here instead: a dialog whose only visible action is Cancel
              reads as though there is no way to confirm. `form` associates the
              button with the form it submits, which the footer sits outside. */}
          <Button
            type="submit"
            form={FORM_ID}
            pending={pending}
            pendingLabel="Running backtest…"
          >
            Run backtest
          </Button>
          <Button variant="secondary" onClick={onCancel} disabled={pending}>
            Cancel
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Alert tone="info">
          The original run is left untouched. Adjust any setting below and run
          it as a new backtest.
        </Alert>
        <StrategyConfigStep
          dataset={dataset}
          configuration={configuration}
          errors={errors}
          formError={formError}
          gridError={gridError}
          datasetMissing={false}
          pending={pending}
          onChange={onChange}
          onReset={onReset}
          onSubmit={onSubmit}
          formId={FORM_ID}
          showSubmitButton={false}
        />
      </div>
    </Dialog>
  );
}

/** Local state helper so the dialog can be driven from a page component. */
export function useDuplicateState(initial: ConfigurationFormState) {
  const [configuration, setConfiguration] = useState(initial);
  return { configuration, setConfiguration };
}
