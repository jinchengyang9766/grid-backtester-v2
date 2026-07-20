"use client";

import { LineChart, type ReferenceLine } from "@/components/charts/line-chart";
import type { DailyEquityProjection } from "@/lib/api/backtest-history-types";
import { SERIES_COLORS, seriesFrom, toCoordinate } from "@/lib/backtests/chart-data";
import { gridLevels, readScalar, type MetricsDocument } from "@/lib/backtests/metrics";

const BOUNDARY_FIELDS: [string, string, string][] = [
  ["baseline", "Baseline", "#1f4e79"],
  ["a_lower", "A lower", "#2e7d32"],
  ["a_upper", "A upper", "#2e7d32"],
  ["c_lower", "C lower", "#c00000"],
  ["c_upper", "C upper", "#c00000"],
];

/**
 * Daily close with the persisted baseline, A/C boundaries, and grid levels.
 *
 * The price line is `DailyEquity.close`, which the engine already stored —
 * PriceBars are never queried. Only levels that are actually persisted in
 * `result_metrics.grid_levels` are drawn; none are generated here, so the
 * chart can never show a level the engine did not use.
 */
export function PriceGridChart({
  dailyEquity,
  metrics,
}: {
  dailyEquity: readonly DailyEquityProjection[];
  metrics: MetricsDocument | null;
}) {
  const price = seriesFrom(dailyEquity, {
    key: "close",
    label: "Daily close",
    color: SERIES_COLORS.price,
    value: (row) => row.close,
    label_: (row) => row.date,
  });

  const references: ReferenceLine[] = [];
  for (const [key, label, color] of BOUNDARY_FIELDS) {
    const stored = readScalar(metrics, key);
    if (stored === null) continue;
    const value = toCoordinate(stored);
    if (value !== null) references.push({ label, value, color });
  }

  const levels = gridLevels(metrics);
  for (const [index, level] of levels.entries()) {
    const value = toCoordinate(level);
    // Faint and unlabelled: individual levels are context, not annotations.
    if (value !== null) {
      references.push({ label: `level-${index}`, value, color: "#94a3b8", faint: true });
    }
  }

  return (
    <div className="space-y-2">
      <LineChart
        title="Price with baseline and grid geometry"
        description={
          "Daily close price with the persisted baseline, A and C zone " +
          "boundaries, and the grid levels the engine recorded."
        }
        series={[price]}
        labels={dailyEquity.map((row) => row.date)}
        referenceLines={references}
        emptyMessage="This run has no stored daily price series."
      />
      <p className="text-xs text-slate-600 dark:text-slate-400">
        {levels.length > 0
          ? `Showing the ${levels.length} grid level(s) stored with this result.`
          : "This result stored no individual grid levels, so only the baseline and zone boundaries are drawn."}
      </p>
    </div>
  );
}
