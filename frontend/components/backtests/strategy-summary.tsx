"use client";

import type {
  ConfigurationFormState,
  StrategyDatasetSummary,
} from "@/lib/backtests/configuration-state";
import { PATH_MODE_LABELS, rateLabel, valueLabel } from "@/lib/backtests/display";
import { dataModeLabel, dateRangeLabel, displayText } from "@/lib/datasets/display";
import type { CommissionFormState } from "@/lib/backtests/configuration-state";

function commissionLabel(commission: CommissionFormState): string {
  const parts: string[] = [];
  parts.push(
    commission.rate_enabled ? `rate ${rateLabel(commission.rate)}` : "rate off",
  );
  parts.push(
    commission.minimum_enabled ? `minimum ${commission.minimum}` : "minimum off",
  );
  parts.push(commission.fixed_enabled ? `fixed ${commission.fixed}` : "fixed off");
  return parts.join(", ");
}

/**
 * Pre-run review.
 *
 * Everything shown comes straight from the form state and the loaded dataset.
 * No return, trade count, equity, or ratio is projected — those exist only
 * after the engine has actually run.
 */
export function StrategySummary({
  dataset,
  configuration,
}: {
  dataset: StrategyDatasetSummary;
  configuration: ConfigurationFormState;
}) {
  const baseline = configuration.baseline.trim();
  const rows: [string, string][] = [
    ["Dataset", `${dataset.name} (ID ${dataset.id})`],
    ["Security", `${displayText(dataset.security_name)} ${displayText(dataset.security_code)}`],
    ["Data mode", dataModeLabel(dataset.data_mode)],
    ["Date range", dateRangeLabel(dataset.start_date, dataset.end_date)],
    ["Rows", String(dataset.row_count)],
    ["Initial cash", configuration.initial_cash],
    ["Initial shares", configuration.initial_shares],
    ["Lot size", configuration.lot_size],
    ["Trade lots", configuration.trade_lots],
    ["Baseline", baseline === "" ? "First close in the dataset" : baseline],
    ["A distance", valueLabel(configuration.a_distance)],
    ["C distance", valueLabel(configuration.c_distance)],
    ["Grid step", valueLabel(configuration.grid_step)],
    [
      "Tick size",
      configuration.tick_size_enabled
        ? `Enabled at ${configuration.tick_size_value}`
        : "Disabled",
    ],
    [
      "Intraday path",
      dataset.data_mode === "OHLCV"
        ? PATH_MODE_LABELS[configuration.ohlc_path_mode]
        : "Not applicable (close-only dataset)",
    ],
    ["Buy commission", commissionLabel(configuration.buy_commission)],
    ["Sell commission", commissionLabel(configuration.sell_commission)],
    [
      "Slippage",
      configuration.slippage.shared
        ? `Shared, ${valueLabel(configuration.slippage.sharedValue)}`
        : `Buy ${valueLabel(configuration.slippage.buy)}; sell ${valueLabel(configuration.slippage.sell)}`,
    ],
    ["Risk-free rate (annual)", rateLabel(configuration.risk_free_rate_annual)],
  ];

  return (
    <section aria-labelledby="review-heading" className="space-y-3">
      <h3 id="review-heading" className="text-sm font-semibold">
        Review before running
      </h3>
      <dl className="grid gap-x-6 gap-y-1.5 rounded-md border border-slate-200 p-3 text-sm sm:grid-cols-2 dark:border-slate-700">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-3">
            <dt className="text-slate-600 dark:text-slate-400">{label}</dt>
            <dd className="text-right font-medium break-words">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
