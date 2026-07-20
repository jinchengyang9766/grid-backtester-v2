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
 * benchmarks. Nothing is recomputed, normalized, or rebased — the benchmarks
 * are plotted on the same absolute equity axis the engine recorded.
 */
export function EquityChart({
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

  return (
    <LineChart
      title="Equity curve"
      description={
        "Daily close equity for the strategy, plotted with both persisted " +
        "buy-and-hold benchmark series. Exact values are listed in the daily " +
        "equity table below."
      }
      series={series}
      labels={labels}
      emptyMessage="This run has no stored daily equity or benchmark series."
    />
  );
}
