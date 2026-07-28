"use client";

import { LineChart, type ReferenceLine } from "@/components/charts/line-chart";
import type {
  DailyEquityProjection,
  TradeProjection,
} from "@/lib/api/backtest-history-types";
import {
  markersFrom,
  SERIES_COLORS,
  seriesFrom,
  toCoordinate,
  type MarkerGroup,
} from "@/lib/backtests/chart-data";
import { readScalar, type MetricsDocument } from "@/lib/backtests/metrics";

const BOUNDARY_FIELDS: [string, string, string][] = [
  ["baseline", "Baseline", "#1f4e79"],
  ["a_lower", "A lower", "#2e7d32"],
  ["a_upper", "A upper", "#2e7d32"],
  ["c_lower", "C lower", "#c00000"],
  ["c_upper", "C upper", "#c00000"],
];

/**
 * Daily close with a marker at every executed trade.
 *
 * The line is `DailyEquity.close`; the markers sit at each trade's persisted
 * `execution_price`, positioned on the same daily date axis. A trade is drawn
 * only where all three of those facts exist: SKIPPED trades never executed at
 * a price, so plotting one would assert a fill that did not happen. Whatever
 * is left out is counted underneath rather than quietly dropped.
 *
 * Trades that share a date land on the same x position; where the stored
 * price is identical too they collapse into one glyph carrying the count, so
 * a busy day stays legible without hiding rows.
 */
export function PriceTradesChart({
  dailyEquity,
  trades,
  metrics,
}: {
  dailyEquity: readonly DailyEquityProjection[];
  trades: readonly TradeProjection[];
  metrics: MetricsDocument | null;
}) {
  const price = seriesFrom(dailyEquity, {
    key: "close",
    label: "Daily close",
    color: SERIES_COLORS.price,
    value: (row) => row.close,
    label_: (row) => row.date,
  });

  // The daily series defines the axis, so a trade is placed by looking its
  // date up rather than by assuming the two series line up row for row.
  const indexByDate = new Map<string, number>();
  dailyEquity.forEach((row, index) => {
    if (!indexByDate.has(row.date)) indexByDate.set(row.date, index);
  });

  const plottable = (trade: TradeProjection) =>
    trade.status === "EXECUTED" && trade.execution_price !== null;

  const buys = markersFrom(
    trades.filter((trade) => trade.side === "BUY" && plottable(trade)),
    {
      key: "buys",
      label: "Buy (executed)",
      shape: "triangle-up",
      color: SERIES_COLORS.buy,
      index: (trade) => indexByDate.get(trade.date) ?? null,
      value: (trade) => trade.execution_price,
      label_: (trade) => trade.date,
    },
  );
  const sells = markersFrom(
    trades.filter((trade) => trade.side === "SELL" && plottable(trade)),
    {
      key: "sells",
      label: "Sell (executed)",
      shape: "triangle-down",
      color: SERIES_COLORS.sell,
      index: (trade) => indexByDate.get(trade.date) ?? null,
      value: (trade) => trade.execution_price,
      label_: (trade) => trade.date,
    },
  );

  const markerGroups: MarkerGroup[] = [buys.group, sells.group];
  const drawn = buys.group.markers.length + sells.group.markers.length;
  const undrawn =
    trades.filter((trade) => !plottable(trade)).length + buys.skipped + sells.skipped;

  const references: ReferenceLine[] = [];
  for (const [key, label, color] of BOUNDARY_FIELDS) {
    const stored = readScalar(metrics, key);
    if (stored === null) continue;
    const value = toCoordinate(stored);
    if (value !== null) references.push({ label, value, color });
  }

  return (
    <div className="space-y-2">
      <LineChart
        title="Price with buy and sell trades"
        description={
          "Daily close price with an upward triangle at every executed buy " +
          "and a downward triangle at every executed sell, each drawn at the " +
          "price the engine recorded for that trade. The persisted baseline " +
          "and A/C zone boundaries are shown as dashed reference lines. Exact " +
          "values are listed in the trades table."
        }
        series={[price]}
        labels={dailyEquity.map((row) => row.date)}
        referenceLines={references}
        markerGroups={markerGroups}
        emptyMessage="This run has no stored daily price series to plot trades against."
        height={300}
      />
      <p className="text-xs text-slate-600 dark:text-slate-400">
        {drawn > 0
          ? `${buys.group.markers.length} buy and ${sells.group.markers.length} sell marker(s) drawn; trades sharing a date and price share one marker.`
          : "No executed trade could be placed on this price axis."}
        {undrawn > 0 &&
          ` ${undrawn} trade(s) are not drawn because they were skipped, recorded no execution price, or fell outside the daily series; every one of them is listed in the trades table.`}
      </p>
    </div>
  );
}
