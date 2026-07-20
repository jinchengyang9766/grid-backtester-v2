"use client";

import Link from "next/link";

import { CommissionInputGroup } from "@/components/backtests/fields/commission-input";
import { DecimalInput, IntegerInput } from "@/components/backtests/fields/decimal-input";
import { DistanceInput } from "@/components/backtests/fields/distance-input";
import { PathModeInput } from "@/components/backtests/fields/path-mode-input";
import { SlippageInputGroup } from "@/components/backtests/fields/slippage-input";
import { TickSizeInput } from "@/components/backtests/fields/tick-size-input";
import { StrategySummary } from "@/components/backtests/strategy-summary";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  cloneCommission,
  type ConfigurationFormState,
  type StrategyDatasetSummary,
} from "@/lib/backtests/configuration-state";
import type { FieldErrors } from "@/lib/backtests/configuration-validation";
import { dataModeLabel, dateRangeLabel, displayText } from "@/lib/datasets/display";

export interface StrategyConfigStepProps {
  dataset: StrategyDatasetSummary;
  configuration: ConfigurationFormState;
  errors: FieldErrors;
  /** Top-level backend message, e.g. a 422 configuration rejection. */
  formError: string | null;
  /** Shown beside the grid section for grid-specific backend codes. */
  gridError: string | null;
  datasetMissing: boolean;
  pending: boolean;
  onChange: (configuration: ConfigurationFormState) => void;
  onReset: () => void;
  onSubmit: () => void;
  /** Overridden when the form is reused inside the duplicate dialog. */
  heading?: string;
  submitLabel?: string;
  submitPendingLabel?: string;
  startingValuesNote?: string;
  showBackLink?: boolean;
}

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-md border border-slate-200 p-4 dark:border-slate-700">
      <h3 className="text-base font-semibold">{title}</h3>
      {description && (
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{description}</p>
      )}
      <div className="mt-4 space-y-4">{children}</div>
    </section>
  );
}

export function StrategyConfigStep({
  dataset,
  configuration,
  errors,
  formError,
  gridError,
  datasetMissing,
  pending,
  onChange,
  onReset,
  onSubmit,
  heading = "Configure strategy",
  submitLabel = "Run backtest",
  submitPendingLabel = "Running backtest…",
  startingValuesNote = "The values below are starting values taken from the specification's example configuration, not recommendations. Review every section before running.",
  showBackLink = true,
}: StrategyConfigStepProps) {
  const update = (patch: Partial<ConfigurationFormState>) =>
    onChange({ ...configuration, ...patch });

  return (
    <form
      className="space-y-6"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
      noValidate
    >
      <div>
        <h2 className="text-lg font-semibold">{heading}</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          Running uses{" "}
          <span className="font-medium break-words">{dataset.name}</span> —{" "}
          {displayText(dataset.security_name)} {displayText(dataset.security_code)},{" "}
          {dataModeLabel(dataset.data_mode)},{" "}
          {dateRangeLabel(dataset.start_date, dataset.end_date)} ({dataset.row_count} rows).
        </p>
      </div>

      {/* Submission problems are announced, not only displayed. */}
      {formError && (
        <Alert
          tone="error"
          title="The backtest could not be started"
          action={
            datasetMissing ? (
              <Link
                href="/datasets"
                className="inline-flex items-center justify-center rounded-md border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              >
                Go to datasets
              </Link>
            ) : undefined
          }
        >
          {formError}
          {datasetMissing && (
            <p className="mt-1">
              This dataset may have been deleted. Your settings are still here.
            </p>
          )}
        </Alert>
      )}

      <p className="text-xs text-slate-600 dark:text-slate-400">
        {startingValuesNote}
      </p>

      <Section
        title="Portfolio"
        description="What the strategy starts with, and how big one order is."
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <DecimalInput
            id="initial-cash"
            label="Initial cash"
            description="Starting cash balance."
            error={errors["configuration.initial_cash"]}
            value={configuration.initial_cash}
            disabled={pending}
            onChange={(initial_cash) => update({ initial_cash })}
          />
          <IntegerInput
            id="initial-shares"
            label="Initial shares"
            description="Shares already held at the start."
            error={errors["configuration.initial_shares"]}
            value={configuration.initial_shares}
            disabled={pending}
            onChange={(initial_shares) => update({ initial_shares })}
          />
          <IntegerInput
            id="lot-size"
            label="Lot size"
            description="Shares per lot."
            error={errors["configuration.lot_size"]}
            value={configuration.lot_size}
            disabled={pending}
            onChange={(lot_size) => update({ lot_size })}
          />
          <IntegerInput
            id="trade-lots"
            label="Trade lots"
            description="Lots per order."
            error={errors["configuration.trade_lots"]}
            value={configuration.trade_lots}
            disabled={pending}
            onChange={(trade_lots) => update({ trade_lots })}
          />
        </div>
        <p className="text-xs text-slate-600 dark:text-slate-400">
          One order trades lot size × trade lots shares.
        </p>
      </Section>

      <Section
        title="Grid geometry"
        description="Where the zones sit and how far apart the execution levels are."
      >
        {gridError && <Alert tone="error">{gridError}</Alert>}

        <DecimalInput
          id="baseline"
          label="Baseline (optional)"
          description="Leave blank to use the dataset's first close as the baseline."
          error={errors["configuration.baseline"]}
          value={configuration.baseline}
          disabled={pending}
          placeholder="First close"
          onChange={(baseline) => update({ baseline })}
        />

        <DistanceInput
          idPrefix="a-distance"
          label="A distance"
          description="The inner zone's distance from the baseline, where the grid trades."
          block={configuration.a_distance}
          valueError={
            errors["configuration.a_distance.value"] ?? errors["configuration.a_distance"]
          }
          disabled={pending}
          onChange={(a_distance) => update({ a_distance })}
        />

        <DistanceInput
          idPrefix="c-distance"
          label="C distance"
          description="The outer boundary's distance from the baseline. Must be greater than A."
          block={configuration.c_distance}
          valueError={
            errors["configuration.c_distance.value"] ?? errors["configuration.c_distance"]
          }
          disabled={pending}
          onChange={(c_distance) => update({ c_distance })}
        />

        <DistanceInput
          idPrefix="grid-step"
          label="Grid step"
          description="The spacing between execution levels inside the A zone."
          block={configuration.grid_step}
          valueError={
            errors["configuration.grid_step.value"] ?? errors["configuration.grid_step"]
          }
          disabled={pending}
          onChange={(grid_step) => update({ grid_step })}
        />
      </Section>

      <Section
        title="Price execution"
        description="How prices are normalized and how each bar is walked."
      >
        <TickSizeInput
          enabled={configuration.tick_size_enabled}
          value={configuration.tick_size_value}
          error={errors["configuration.tick_size.value"]}
          disabled={pending}
          onEnabledChange={(tick_size_enabled) => update({ tick_size_enabled })}
          onValueChange={(tick_size_value) => update({ tick_size_value })}
        />
        <PathModeInput
          dataMode={dataset.data_mode}
          value={configuration.ohlc_path_mode}
          disabled={pending}
          onChange={(ohlc_path_mode) => update({ ohlc_path_mode })}
        />
      </Section>

      <Section title="Fees" description="Buy and sell commissions are configured separately.">
        <div className="grid gap-4 lg:grid-cols-2">
          <CommissionInputGroup
            idPrefix="buy-commission"
            legend="Buy commission"
            commission={configuration.buy_commission}
            errors={errors}
            errorPrefix="configuration.buy_commission"
            disabled={pending}
            onChange={(buy_commission) => update({ buy_commission })}
          />
          <CommissionInputGroup
            idPrefix="sell-commission"
            legend="Sell commission"
            commission={configuration.sell_commission}
            errors={errors}
            errorPrefix="configuration.sell_commission"
            disabled={pending}
            onChange={(sell_commission) => update({ sell_commission })}
          />
        </div>
        <Button
          variant="secondary"
          disabled={pending}
          onClick={() =>
            // Deep copy, so the two sides never share nested state.
            update({ sell_commission: cloneCommission(configuration.buy_commission) })
          }
        >
          Copy buy settings to sell
        </Button>
      </Section>

      <Section title="Slippage" description="The price concession assumed on each execution.">
        <SlippageInputGroup
          slippage={configuration.slippage}
          errors={errors}
          disabled={pending}
          onChange={(slippage) => update({ slippage })}
        />
      </Section>

      <Section title="Risk assumptions">
        <DecimalInput
          id="risk-free-rate"
          label="Annual risk-free rate"
          description="A decimal fraction per year: 0.02 is 2%. Used for the Sharpe ratio. Enter 0 to ignore it."
          error={errors["configuration.risk_free_rate_annual"]}
          value={configuration.risk_free_rate_annual}
          disabled={pending}
          onChange={(risk_free_rate_annual) => update({ risk_free_rate_annual })}
        />
      </Section>

      <StrategySummary dataset={dataset} configuration={configuration} />

      <div className="flex flex-wrap gap-2">
        <Button type="submit" pending={pending} pendingLabel={submitPendingLabel}>
          {submitLabel}
        </Button>
        <Button variant="secondary" onClick={onReset} disabled={pending}>
          Reset to defaults
        </Button>
        {showBackLink && (
          <Link
            href="/datasets"
            className="inline-flex items-center justify-center rounded-md px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Back to datasets
          </Link>
        )}
      </div>
    </form>
  );
}
