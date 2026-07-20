"use client";

import { LineChart } from "@/components/charts/line-chart";
import type { DailyEquityProjection } from "@/lib/api/backtest-history-types";
import { SERIES_COLORS, seriesFrom } from "@/lib/backtests/chart-data";
import { compareDecimals } from "@/lib/backtests/decimal-string";

/**
 * The persisted drawdown series.
 *
 * `DailyEquity.drawdown` is read directly — running peaks are never
 * recalculated, and drawdown is never derived from the equity series, because
 * either would risk disagreeing with the stored maximum-drawdown metric.
 * Negative values are preserved as stored.
 */
export function DrawdownChart({
  dailyEquity,
}: {
  dailyEquity: readonly DailyEquityProjection[];
}) {
  const series = seriesFrom(dailyEquity, {
    key: "drawdown",
    label: "Drawdown",
    color: SERIES_COLORS.drawdown,
    value: (row) => row.drawdown,
    label_: (row) => row.date,
  });

  // Extremes are found by exact decimal comparison, then shown as the stored
  // strings — no rounding, no float.
  let worst: DailyEquityProjection | null = null;
  for (const row of dailyEquity) {
    if (worst === null || (compareDecimals(row.drawdown, worst.drawdown) ?? 0) < 0) {
      worst = row;
    }
  }

  return (
    <div className="space-y-2">
      <LineChart
        title="Drawdown"
        description={
          "Daily drawdown as recorded by the engine, with a zero reference " +
          "line. Negative values indicate a fall below the running peak."
        }
        series={[series]}
        labels={dailyEquity.map((row) => row.date)}
        referenceLines={[{ label: "0", value: 0, color: "#666666" }]}
        emptyMessage="This run has no stored drawdown series."
      />
      {worst !== null && (
        <p className="text-xs text-slate-600 dark:text-slate-400">
          Deepest recorded drawdown:{" "}
          <span className="font-medium tabular-nums">{worst.drawdown}</span> on{" "}
          {worst.date}.
        </p>
      )}
    </div>
  );
}
