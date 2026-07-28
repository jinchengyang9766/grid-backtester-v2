"use client";

import { LineChart } from "@/components/charts/line-chart";
import type { DailyEquityProjection } from "@/lib/api/backtest-history-types";
import {
  rebaseSeries,
  SERIES_COLORS,
  SERIES_DASHES,
  seriesFrom,
  type ChartSeries,
} from "@/lib/backtests/chart-data";
import { benchmarkPoints, type MetricsDocument } from "@/lib/backtests/metrics";

const BASE = 100;

/**
 * The same three persisted series, each rebased to 100 at its first point.
 *
 * This is a display transform applied at the chart-coordinate stage, not a
 * metric: no stored value is altered, and the reported total and annualized
 * returns in `result_metrics` remain the only figures the dashboard quotes as
 * results. Rebasing exists because the strategy and the two benchmarks start
 * from different capital, so their absolute curves cannot be compared by eye.
 *
 * A series whose first stored point is zero has no defined ratio, so it is
 * omitted and named underneath rather than drawn as a flat line.
 */
export function NormalizedPerformanceChart({
  dailyEquity,
  metrics,
}: {
  dailyEquity: readonly DailyEquityProjection[];
  metrics: MetricsDocument | null;
}) {
  const raw: ChartSeries[] = [
    seriesFrom(dailyEquity, {
      key: "strategy",
      label: "Strategy",
      color: SERIES_COLORS.strategy,
      dash: SERIES_DASHES.strategy,
      value: (row) => row.equity,
      label_: (row) => row.date,
    }),
    seriesFrom(benchmarkPoints(metrics, "benchmark1"), {
      key: "benchmark1",
      label: "Benchmark 1 (hold initial portfolio)",
      color: SERIES_COLORS.benchmark1,
      dash: SERIES_DASHES.benchmark1,
      value: (point) => point.equity,
      label_: (point) => point.date,
    }),
    seriesFrom(benchmarkPoints(metrics, "benchmark2"), {
      key: "benchmark2",
      label: "Benchmark 2 (invest cash on day one)",
      color: SERIES_COLORS.benchmark2,
      dash: SERIES_DASHES.benchmark2,
      value: (point) => point.equity,
      label_: (point) => point.date,
    }),
  ];

  const series: ChartSeries[] = [];
  const undefinedBase: string[] = [];
  for (const entry of raw) {
    if (entry.points.length === 0) continue;
    const rebased = rebaseSeries(entry, BASE);
    if (rebased === null) undefinedBase.push(entry.label);
    else series.push(rebased);
  }

  const labels =
    dailyEquity.length > 0
      ? dailyEquity.map((row) => row.date)
      : benchmarkPoints(metrics, "benchmark1").map((point) => point.date);

  return (
    <div className="space-y-2">
      <LineChart
        title="Normalized performance (each series rebased to 100)"
        description={
          "A normalized comparison, not a reported result: the strategy and " +
          "each available benchmark are scaled so their first stored point " +
          "equals 100, which makes their shapes comparable even though they " +
          "start from different amounts of capital. A value of 110 means the " +
          "series stands 10 percent above where it started."
        }
        series={series}
        labels={labels}
        referenceLines={[{ label: "100 (start)", value: BASE, color: "#666666" }]}
        emptyMessage="This run has no stored series to normalize."
      />
      <p className="text-xs text-slate-600 dark:text-slate-400">
        Normalized for visual comparison only — every series starts at {BASE}.
        The exact stored equity values are in the daily equity table, and the
        reported returns are in the metric sections.
        {undefinedBase.length > 0 &&
          ` ${undefinedBase.join(" and ")} started at zero, so no ratio is defined and ${
            undefinedBase.length === 1 ? "it is" : "they are"
          } not drawn.`}
      </p>
    </div>
  );
}
