/**
 * Reading the persisted `result_metrics` document.
 *
 * Everything here is a lookup or a relabel. No metric is derived, averaged,
 * or recomputed from the normalized series: the stored document is what the
 * engine actually produced, and a second calculation in the browser could
 * disagree with it. Values are returned as the exact strings the backend
 * stored.
 *
 * The canonical shape (see `app/backtests/serialization.py`):
 *
 *   { initial_equity, baseline, a_lower, a_upper, c_lower, c_upper,
 *     grid_step, grid_levels[], final_state{…},
 *     metrics: { strategy{…}, trade_costs{…}, zones{…}, first_return{…},
 *                benchmark1{…}, benchmark2{…},
 *                benchmark2_day_one_commission, benchmark2_day_one_slippage_cost },
 *     benchmark1: { points[], day_one_purchase }, benchmark2: { … } }
 */

export type MetricsDocument = Record<string, unknown>;

export function readNode(source: unknown, ...path: string[]): unknown {
  let current: unknown = source;
  for (const key of path) {
    if (typeof current !== "object" || current === null) return undefined;
    current = (current as Record<string, unknown>)[key];
  }
  return current;
}

/** A scalar rendered verbatim; objects/arrays return null. */
export function readScalar(source: unknown, ...path: string[]): string | null {
  const value = readNode(source, ...path);
  if (value === null || value === undefined) return null;
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return null;
}

export interface MetricRow {
  label: string;
  /** The stored value, or null when absent. */
  value: string | null;
  /** True when the stored value is a ratio worth showing as a percentage. */
  ratio?: boolean;
}

export interface MetricSection {
  title: string;
  rows: MetricRow[];
}

const EQUITY_SERIES_FIELDS: [string, string, boolean][] = [
  ["initial_equity", "Initial equity", false],
  ["final_equity", "Final equity", false],
  ["net_profit", "Net profit", false],
  ["total_return", "Total return", true],
  ["annualized_return", "Annualized return", true],
  ["maximum_drawdown", "Maximum drawdown", true],
  ["sharpe_ratio", "Sharpe ratio", false],
];

function equitySeriesRows(source: unknown): MetricRow[] {
  return EQUITY_SERIES_FIELDS.map(([key, label, ratio]) => ({
    label,
    value: readScalar(source, key),
    ratio,
  }));
}

/** Headline figures for the top of the dashboard. */
export function headlineRows(metrics: MetricsDocument | null): MetricRow[] {
  if (metrics === null) return [];
  const strategy = readNode(metrics, "metrics", "strategy");
  return [
    { label: "Final equity", value: readScalar(strategy, "final_equity") },
    { label: "Net profit", value: readScalar(strategy, "net_profit") },
    { label: "Total return", value: readScalar(strategy, "total_return"), ratio: true },
    {
      label: "Maximum drawdown",
      value: readScalar(strategy, "maximum_drawdown"),
      ratio: true,
    },
    { label: "Sharpe ratio", value: readScalar(strategy, "sharpe_ratio") },
    {
      label: "Executed trades",
      value: readScalar(metrics, "metrics", "trade_costs", "executed_trades"),
    },
  ];
}

export function strategySection(metrics: MetricsDocument | null): MetricSection {
  return {
    title: "Strategy performance",
    rows: equitySeriesRows(readNode(metrics, "metrics", "strategy")),
  };
}

export function costSection(metrics: MetricsDocument | null): MetricSection {
  const costs = readNode(metrics, "metrics", "trade_costs");
  return {
    title: "Costs and trade counts",
    rows: [
      { label: "Total commission", value: readScalar(costs, "total_commission") },
      { label: "Total slippage cost", value: readScalar(costs, "total_slippage_cost") },
      { label: "Executed trades", value: readScalar(costs, "executed_trades") },
      { label: "Skipped trades", value: readScalar(costs, "skipped_trades") },
      { label: "Buy count", value: readScalar(costs, "buy_count") },
      { label: "Sell count", value: readScalar(costs, "sell_count") },
      {
        label: "Benchmark 2 day-one commission",
        value: readScalar(metrics, "metrics", "benchmark2_day_one_commission"),
      },
      {
        label: "Benchmark 2 day-one slippage cost",
        value: readScalar(metrics, "metrics", "benchmark2_day_one_slippage_cost"),
      },
    ],
  };
}

export function zoneSection(metrics: MetricsDocument | null): MetricSection {
  const zones = readNode(metrics, "metrics", "zones");
  const counts = readNode(zones, "zone_event_counts");
  const eventRows: MetricRow[] =
    typeof counts === "object" && counts !== null
      ? Object.entries(counts as Record<string, unknown>).map(([key, value]) => ({
          label: `Zone event: ${key}`,
          value: value === null || value === undefined ? null : String(value),
        }))
      : [];
  return {
    title: "Zone statistics",
    rows: [
      { label: "Days closed in A zone", value: readScalar(zones, "days_closed_in_a_zone") },
      { label: "Days closed in C zone", value: readScalar(zones, "days_closed_in_c_zone") },
      { label: "Days closed outside C", value: readScalar(zones, "days_closed_outside_c") },
      ...eventRows,
    ],
  };
}

export function firstReturnSection(metrics: MetricsDocument | null): MetricSection {
  const first = readNode(metrics, "metrics", "first_return");
  return {
    title: "First return to initial share position",
    rows: [
      { label: "Equity at first return", value: readScalar(first, "equity") },
      { label: "Days until first return", value: readScalar(first, "days") },
    ],
  };
}

export function finalStateSection(metrics: MetricsDocument | null): MetricSection {
  const state = readNode(metrics, "final_state");
  return {
    title: "Final portfolio state",
    rows: [
      { label: "Cash", value: readScalar(state, "cash") },
      { label: "Shares", value: readScalar(state, "shares") },
      { label: "Market cursor", value: readScalar(state, "market_cursor") },
      { label: "Trade anchor", value: readScalar(state, "trade_anchor") },
      { label: "Zone state", value: readScalar(state, "zone_state") },
    ],
  };
}

export function gridGeometrySection(metrics: MetricsDocument | null): MetricSection {
  const levels = readNode(metrics, "grid_levels");
  return {
    title: "Baseline and grid geometry",
    rows: [
      { label: "Baseline", value: readScalar(metrics, "baseline") },
      { label: "A zone lower", value: readScalar(metrics, "a_lower") },
      { label: "A zone upper", value: readScalar(metrics, "a_upper") },
      { label: "C zone lower", value: readScalar(metrics, "c_lower") },
      { label: "C zone upper", value: readScalar(metrics, "c_upper") },
      { label: "Grid step size", value: readScalar(metrics, "grid_step") },
      {
        label: "Grid level count",
        value: Array.isArray(levels) ? String(levels.length) : null,
      },
    ],
  };
}

/** Benchmark 1 and 2 summary metrics, from the stored metrics block. */
export function benchmarkSections(metrics: MetricsDocument | null): MetricSection[] {
  return [
    {
      title: "Benchmark 1 — same initial portfolio, no trades",
      rows: equitySeriesRows(readNode(metrics, "metrics", "benchmark1")),
    },
    {
      title: "Benchmark 2 — invest available cash on day one",
      rows: equitySeriesRows(readNode(metrics, "metrics", "benchmark2")),
    },
  ];
}

const DAY_ONE_FIELDS: [string, string][] = [
  ["reference_price", "Reference price"],
  ["tick_price", "Tick price"],
  ["execution_price", "Execution price"],
  ["lots", "Lots"],
  ["shares_purchased", "Shares purchased"],
  ["notional", "Notional"],
  ["commission", "Commission"],
  ["slippage_cost", "Slippage cost"],
  ["cash_after", "Cash after"],
  ["shares_after", "Shares after"],
];

export function benchmarkTwoDayOneSection(
  metrics: MetricsDocument | null,
): MetricSection | null {
  const dayOne = readNode(metrics, "benchmark2", "day_one_purchase");
  if (typeof dayOne !== "object" || dayOne === null) return null;
  return {
    title: "Benchmark 2 day-one purchase",
    rows: DAY_ONE_FIELDS.map(([key, label]) => ({
      label,
      value: readScalar(dayOne, key),
    })),
  };
}

/** A persisted benchmark equity point. */
export interface BenchmarkPoint {
  date: string;
  close: string;
  cash: string;
  shares: number;
  equity: string;
}

/** The stored benchmark series, exactly as persisted; never recomputed. */
export function benchmarkPoints(
  metrics: MetricsDocument | null,
  key: "benchmark1" | "benchmark2",
): BenchmarkPoint[] {
  const points = readNode(metrics, key, "points");
  if (!Array.isArray(points)) return [];
  const result: BenchmarkPoint[] = [];
  for (const raw of points) {
    if (typeof raw !== "object" || raw === null) continue;
    const point = raw as Record<string, unknown>;
    if (typeof point.date === "string" && typeof point.equity === "string") {
      result.push({
        date: point.date,
        close: typeof point.close === "string" ? point.close : "",
        cash: typeof point.cash === "string" ? point.cash : "",
        shares: typeof point.shares === "number" ? point.shares : 0,
        equity: point.equity,
      });
    }
  }
  return result;
}

/** Persisted grid levels, when the document carries them. */
export function gridLevels(metrics: MetricsDocument | null): string[] {
  const levels = readNode(metrics, "grid_levels");
  if (!Array.isArray(levels)) return [];
  return levels.filter((level): level is string => typeof level === "string");
}

/**
 * Keys this module renders under a named section. Anything outside this set
 * is surfaced in a labelled "additional stored values" fallback rather than
 * being dropped or dumped as raw JSON.
 */
const KNOWN_TOP_LEVEL = new Set([
  "initial_equity",
  "baseline",
  "a_lower",
  "a_upper",
  "c_lower",
  "c_upper",
  "grid_step",
  "grid_levels",
  "metrics",
  "benchmark1",
  "benchmark2",
  "final_state",
]);

export function additionalRows(metrics: MetricsDocument | null): MetricRow[] {
  if (metrics === null) return [];
  const rows: MetricRow[] = [];
  for (const [key, value] of Object.entries(metrics)) {
    if (KNOWN_TOP_LEVEL.has(key)) continue;
    if (typeof value === "object" && value !== null) continue;
    rows.push({ label: key, value: value === null ? null : String(value) });
  }
  return rows;
}

/**
 * Flatten a metrics document into deterministic dotted paths, for the
 * side-by-side comparison table.
 */
export function flattenMetrics(
  metrics: MetricsDocument | null,
  prefix = "",
): Map<string, string | null> {
  const flat = new Map<string, string | null>();
  if (metrics === null) return flat;

  for (const [key, value] of Object.entries(metrics)) {
    const path = prefix === "" ? key : `${prefix}.${key}`;
    if (value === null || value === undefined) {
      flat.set(path, null);
    } else if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      flat.set(path, String(value));
    } else if (Array.isArray(value)) {
      // Long point series would swamp the table; report the length instead.
      flat.set(`${path}.length`, String(value.length));
    } else if (typeof value === "object") {
      for (const [innerPath, innerValue] of flattenMetrics(
        value as MetricsDocument,
        path,
      )) {
        flat.set(innerPath, innerValue);
      }
    }
  }
  return flat;
}
