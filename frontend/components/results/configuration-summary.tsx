import { MetricGrid } from "@/components/results/metric-grid";
import { decimalTimesHundred, isDecimalString, trimTrailingZeros } from "@/lib/backtests/decimal-string";
import { PATH_MODE_LABELS } from "@/lib/backtests/display";
import { readNode, readScalar, type MetricRow } from "@/lib/backtests/metrics";
import { EMPTY_VALUE } from "@/lib/datasets/display";

/**
 * The canonical stored configuration, in readable groups.
 *
 * Values are shown exactly as persisted. No grid is generated and no engine
 * behaviour is re-derived — this is a presentation of the document the run
 * was executed with.
 */

function valueBlockText(source: unknown, key: string): string {
  const block = readNode(source, key);
  if (typeof block !== "object" || block === null) return EMPTY_VALUE;
  const mode = readScalar(block, "mode");
  const value = readScalar(block, "value");
  if (value === null) return EMPTY_VALUE;
  if (mode === "PERCENT" && isDecimalString(value)) {
    const percent = decimalTimesHundred(value);
    return percent === null
      ? `${value} (percent mode)`
      : `${value} (${trimTrailingZeros(percent)}%, percent mode)`;
  }
  return `${value} (${mode === "FIXED" ? "fixed" : String(mode)} mode)`;
}

function enabledText(source: unknown, key: string): string {
  const value = readNode(source, key);
  if (value === null || value === undefined) return EMPTY_VALUE;
  return value ? "Enabled" : "Disabled";
}

function commissionRows(source: unknown, label: string): MetricRow[] {
  const commission = readNode(source, label === "Buy" ? "buy_commission" : "sell_commission");
  return [
    { label: `${label} rate`, value: enabledText(commission, "rate_enabled") },
    { label: `${label} rate value`, value: readScalar(commission, "rate"), ratio: true },
    { label: `${label} minimum`, value: enabledText(commission, "minimum_enabled") },
    { label: `${label} minimum value`, value: readScalar(commission, "minimum") },
    { label: `${label} fixed fee`, value: enabledText(commission, "fixed_enabled") },
    { label: `${label} fixed value`, value: readScalar(commission, "fixed") },
  ];
}

function slippageRows(configuration: Record<string, unknown>): MetricRow[] {
  const slippage = readNode(configuration, "slippage");
  const shared = readNode(slippage, "shared");
  if (shared) {
    return [
      { label: "Slippage applies to", value: "Both sides (shared)" },
      { label: "Slippage mode", value: readScalar(slippage, "mode") },
      { label: "Slippage value", value: readScalar(slippage, "value") },
    ];
  }
  return [
    { label: "Slippage applies to", value: "Buy and sell separately" },
    { label: "Buy slippage mode", value: readScalar(slippage, "buy", "mode") },
    { label: "Buy slippage value", value: readScalar(slippage, "buy", "value") },
    { label: "Sell slippage mode", value: readScalar(slippage, "sell", "mode") },
    { label: "Sell slippage value", value: readScalar(slippage, "sell", "value") },
  ];
}

export function ConfigurationSummary({
  configuration,
  dataMode,
}: {
  configuration: Record<string, unknown>;
  dataMode: string;
}) {
  const baseline = readScalar(configuration, "baseline");
  const pathMode = readScalar(configuration, "ohlc_path_mode");

  const sections: { title: string; rows: MetricRow[] }[] = [
    {
      title: "Portfolio",
      rows: [
        { label: "Initial cash", value: readScalar(configuration, "initial_cash") },
        { label: "Initial shares", value: readScalar(configuration, "initial_shares") },
        { label: "Lot size", value: readScalar(configuration, "lot_size") },
        { label: "Trade lots", value: readScalar(configuration, "trade_lots") },
      ],
    },
    {
      title: "Grid geometry",
      rows: [
        {
          label: "Baseline",
          value: baseline === null ? "First close in the dataset" : baseline,
        },
        { label: "A distance", value: valueBlockText(configuration, "a_distance") },
        { label: "C distance", value: valueBlockText(configuration, "c_distance") },
        { label: "Grid step", value: valueBlockText(configuration, "grid_step") },
      ],
    },
    {
      title: "Price execution",
      rows: [
        { label: "Tick size", value: enabledText(readNode(configuration, "tick_size"), "enabled") },
        {
          label: "Tick size value",
          value: readScalar(configuration, "tick_size", "value"),
        },
        {
          label: "Intraday path mode",
          value:
            dataMode !== "OHLCV"
              ? "Not applicable (close-only dataset)"
              : pathMode === null
                ? EMPTY_VALUE
                : (PATH_MODE_LABELS[pathMode as keyof typeof PATH_MODE_LABELS] ?? pathMode),
        },
      ],
    },
    { title: "Buy commission", rows: commissionRows(configuration, "Buy") },
    { title: "Sell commission", rows: commissionRows(configuration, "Sell") },
    { title: "Slippage", rows: slippageRows(configuration) },
    {
      title: "Risk assumptions",
      rows: [
        {
          label: "Annual risk-free rate",
          value: readScalar(configuration, "risk_free_rate_annual"),
          ratio: true,
        },
      ],
    },
  ];

  return (
    <div className="space-y-5">
      {sections.map((section) => (
        <section key={section.title} className="space-y-2">
          <h3 className="text-sm font-semibold">{section.title}</h3>
          <MetricGrid rows={section.rows} />
        </section>
      ))}
    </div>
  );
}
