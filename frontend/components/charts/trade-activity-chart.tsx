"use client";

import { BarChart } from "@/components/charts/bar-chart";
import type {
  DailyEquityProjection,
  TradeProjection,
} from "@/lib/api/backtest-history-types";
import {
  countByIndex,
  SERIES_COLORS,
  type BarSeries,
} from "@/lib/backtests/chart-data";
import { readScalar, type MetricsDocument } from "@/lib/backtests/metrics";

/**
 * How trading clustered over the run: executed buys and sells per day.
 *
 * Only whole rows are counted, and only on the daily date axis the rest of
 * the dashboard uses. The totals quoted underneath are read from the stored
 * `trade_costs` block rather than re-tallied, so the caption always agrees
 * with the metric tables even if a trade falls outside the daily series.
 */
export function TradeActivityChart({
  dailyEquity,
  trades,
  metrics,
}: {
  dailyEquity: readonly DailyEquityProjection[];
  trades: readonly TradeProjection[];
  metrics: MetricsDocument | null;
}) {
  const indexByDate = new Map<string, number>();
  dailyEquity.forEach((row, index) => {
    if (!indexByDate.has(row.date)) indexByDate.set(row.date, index);
  });

  const position = (trade: TradeProjection) => indexByDate.get(trade.date) ?? null;
  const executed = trades.filter((trade) => trade.status === "EXECUTED");

  const series: BarSeries[] = [
    {
      key: "buys",
      label: "Executed buys",
      color: SERIES_COLORS.buy,
      counts: countByIndex(
        executed.filter((trade) => trade.side === "BUY"),
        dailyEquity.length,
        position,
      ),
    },
    {
      key: "sells",
      label: "Executed sells",
      color: SERIES_COLORS.sell,
      hatched: true,
      counts: countByIndex(
        executed.filter((trade) => trade.side === "SELL"),
        dailyEquity.length,
        position,
      ),
    },
  ];

  const buyCount = readScalar(metrics, "metrics", "trade_costs", "buy_count");
  const sellCount = readScalar(metrics, "metrics", "trade_costs", "sell_count");

  return (
    <div className="space-y-2">
      <BarChart
        title="Trade activity per day"
        description={
          "Executed buys and sells counted per trading day and stacked, so " +
          "the taller the bar the busier the day. Buys are solid and sells " +
          "are hatched, so the two are distinguishable without colour."
        }
        series={series}
        labels={dailyEquity.map((row) => row.date)}
        emptyMessage="This run recorded no executed trades on the daily axis."
      />
      {buyCount !== null && sellCount !== null && (
        <p className="text-xs text-slate-600 dark:text-slate-400">
          The stored result records{" "}
          <span className="font-medium tabular-nums">{buyCount}</span> buy and{" "}
          <span className="font-medium tabular-nums">{sellCount}</span> sell
          trades in total. Every one is listed in the trades table.
        </p>
      )}
    </div>
  );
}
