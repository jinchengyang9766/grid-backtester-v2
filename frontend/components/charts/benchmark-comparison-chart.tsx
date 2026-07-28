"use client";

import { LineChart } from "@/components/charts/line-chart";
import type { DailyEquityProjection } from "@/lib/api/backtest-history-types";
import {
  SERIES_COLORS,
  SERIES_DASHES,
  seriesFrom,
  type ChartSeries,
} from "@/lib/backtests/chart-data";
import { benchmarkPoints, type MetricsDocument } from "@/lib/backtests/metrics";

/**
 * Strategy equity against both persisted buy-and-hold benchmarks.
 *
 * All three series come straight from stored rows: DailyEquity for the
 * strategy, and `result_metrics.benchmark1/2.points[].equity` for the
 * benchmarks. Nothing is recomputed or rebased — the benchmarks are plotted
 * on the same absolute equity axis the engine recorded, which is why a
 * benchmark that started from different capital sits at a different level.
 */
export function BenchmarkComparisonChart({
  dailyEquity,
  metrics,
}: {
  dailyEquity: readonly DailyEquityProjection[];
  metrics: MetricsDocument | null;
}) {
  const benchmark1 = benchmarkPoints(metrics, "benchmark1");
  const benchmark2 = benchmarkPoints(metrics, "benchmark2");

  const series: ChartSeries[] = [
    seriesFrom(dailyEquity, {
      key: "strategy",
      label: "Strategy equity",
      color: SERIES_COLORS.strategy,
      dash: SERIES_DASHES.strategy,
      value: (row) => row.equity,
      label_: (row) => row.date,
    }),
    seriesFrom(benchmark1, {
      key: "benchmark1",
      label: "Benchmark 1 (hold initial portfolio)",
      color: SERIES_COLORS.benchmark1,
      dash: SERIES_DASHES.benchmark1,
      value: (point) => point.equity,
      label_: (point) => point.date,
    }),
    seriesFrom(benchmark2, {
      key: "benchmark2",
      label: "Benchmark 2 (invest cash on day one)",
      color: SERIES_COLORS.benchmark2,
      dash: SERIES_DASHES.benchmark2,
      value: (point) => point.equity,
      label_: (point) => point.date,
    }),
  ];

  // The strategy series defines the date axis; benchmarks share the same
  // persisted dates, so index alignment matches date alignment.
  const labels =
    dailyEquity.length > 0
      ? dailyEquity.map((row) => row.date)
      : benchmark1.map((point) => point.date);

  const missing: string[] = [];
  if (benchmark1.length === 0) missing.push("Benchmark 1");
  if (benchmark2.length === 0) missing.push("Benchmark 2");

  return (
    <div className="space-y-2">
      <LineChart
        title="Strategy against both benchmarks"
        description={
          "Absolute equity for the strategy plotted with both persisted " +
          "buy-and-hold benchmark series. Each line is distinguished by dash " +
          "pattern as well as colour, and exact values are listed in the " +
          "benchmark metric tables."
        }
        series={series}
        labels={labels}
        emptyMessage="This run has no stored daily equity or benchmark series."
      />
      {missing.length > 0 && (
        <p className="text-xs text-slate-600 dark:text-slate-400">
          {missing.join(" and ")} stored no equity points for this run, so{" "}
          {missing.length === 1 ? "that series is" : "those series are"} absent
          from the chart rather than estimated.
        </p>
      )}
    </div>
  );
}
