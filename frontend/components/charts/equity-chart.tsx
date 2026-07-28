"use client";

import { LineChart } from "@/components/charts/line-chart";
import type { DailyEquityProjection } from "@/lib/api/backtest-history-types";
import {
  SERIES_COLORS,
  SERIES_DASHES,
  seriesFrom,
} from "@/lib/backtests/chart-data";
import { readScalar, type MetricsDocument } from "@/lib/backtests/metrics";

/**
 * The strategy's own equity curve, on its own.
 *
 * Every point is a stored `DailyEquity.equity` value — nothing is smoothed,
 * rebased, or recomputed. The initial and final figures quoted beneath come
 * from `result_metrics`, so the caption cannot disagree with the metric
 * tables. The benchmark comparison lives in its own chart, so this one shows
 * the strategy's shape without three lines competing for the axis.
 */
export function EquityChart({
  dailyEquity,
  metrics,
}: {
  dailyEquity: readonly DailyEquityProjection[];
  metrics: MetricsDocument | null;
}) {
  const strategy = seriesFrom(dailyEquity, {
    key: "strategy",
    label: "Strategy equity",
    color: SERIES_COLORS.strategy,
    dash: SERIES_DASHES.strategy,
    value: (row) => row.equity,
    label_: (row) => row.date,
  });

  const initial = readScalar(metrics, "metrics", "strategy", "initial_equity");
  const final = readScalar(metrics, "metrics", "strategy", "final_equity");

  return (
    <div className="space-y-2">
      <LineChart
        title="Strategy equity curve"
        description={
          "Daily close equity for the strategy, exactly as the engine stored " +
          "it. Exact values are listed in the daily equity table."
        }
        series={[strategy]}
        labels={dailyEquity.map((row) => row.date)}
        emptyMessage="This run has no stored daily equity series."
      />
      {initial !== null && final !== null && (
        <p className="text-xs text-slate-600 dark:text-slate-400">
          Stored initial equity <span className="font-medium tabular-nums">{initial}</span>,
          final equity <span className="font-medium tabular-nums">{final}</span> over{" "}
          {dailyEquity.length} recorded day(s).
        </p>
      )}
    </div>
  );
}
