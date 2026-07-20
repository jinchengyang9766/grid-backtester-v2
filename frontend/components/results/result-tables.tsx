"use client";

/**
 * The four normalized result series.
 *
 * Every cell is the exact string the backend projected — no value is parsed,
 * rounded, or reformatted, and null renders as a neutral dash. Long series
 * are revealed progressively for readability; no row is ever dropped, and the
 * full count is always shown.
 *
 * The projections carry each row's own `id` but no `event_id` or
 * `backtest_run_id`, so no internal foreign key is displayed.
 */

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Table, TableScroll, Td, Th } from "@/components/ui/table";
import type {
  DailyEquityProjection,
  EventEquityProjection,
  TradeProjection,
  ZoneEventProjection,
} from "@/lib/api/backtest-history-types";
import { EMPTY_VALUE, humanizeCode } from "@/lib/datasets/display";

const PAGE_SIZE = 50;

function cell(value: string | null): string {
  return value === null || value === "" ? EMPTY_VALUE : value;
}

function useVisibleRows<T>(rows: readonly T[]) {
  const [visible, setVisible] = useState(PAGE_SIZE);
  const shown = rows.slice(0, visible);
  const remaining = rows.length - shown.length;
  const showMore = () => setVisible((current) => current + PAGE_SIZE);
  return { shown, remaining, showMore };
}

function SeriesFrame({
  title,
  total,
  shownCount,
  remaining,
  onShowMore,
  emptyTitle,
  emptyBody,
  children,
}: {
  title: string;
  total: number;
  shownCount: number;
  remaining: number;
  onShowMore: () => void;
  emptyTitle: string;
  emptyBody: string;
  children: React.ReactNode;
}) {
  if (total === 0) {
    return (
      <section className="space-y-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <EmptyState title={emptyTitle}>{emptyBody}</EmptyState>
      </section>
    );
  }
  return (
    <section className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="text-xs text-slate-600 dark:text-slate-400">
          Showing {shownCount} of {total} row{total === 1 ? "" : "s"}
        </p>
      </div>
      {children}
      {remaining > 0 && (
        <Button variant="secondary" onClick={onShowMore}>
          Show {Math.min(remaining, PAGE_SIZE)} more
        </Button>
      )}
    </section>
  );
}

export function TradesTable({ rows }: { rows: readonly TradeProjection[] }) {
  const { shown, remaining, showMore } = useVisibleRows(rows);
  return (
    <SeriesFrame
      title="Trades"
      total={rows.length}
      shownCount={shown.length}
      remaining={remaining}
      onShowMore={showMore}
      emptyTitle="No trades"
      emptyBody="This run recorded no trade events."
    >
      <TableScroll label="Trades">
        <Table caption="Every trade this run recorded, in global event order">
          <thead>
            <tr>
              <Th numeric>Seq</Th>
              <Th>Date</Th>
              <Th>Side</Th>
              <Th numeric>Grid price</Th>
              <Th numeric>Execution price</Th>
              <Th numeric>Shares</Th>
              <Th numeric>Notional</Th>
              <Th numeric>Commission</Th>
              <Th numeric>Slippage cost</Th>
              <Th numeric>Cash after</Th>
              <Th numeric>Shares after</Th>
              <Th numeric>Equity after</Th>
              <Th>Status</Th>
              <Th>Skip reason</Th>
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <tr key={row.id}>
                <Td numeric>{row.event_sequence}</Td>
                <Td>{row.date}</Td>
                <Td>{row.side}</Td>
                <Td numeric>{row.grid_price}</Td>
                <Td numeric>{cell(row.execution_price)}</Td>
                <Td numeric>{row.shares}</Td>
                <Td numeric>{cell(row.notional)}</Td>
                <Td numeric>{cell(row.commission)}</Td>
                <Td numeric>{cell(row.slippage_cost)}</Td>
                <Td numeric>{row.cash_after}</Td>
                <Td numeric>{row.shares_after}</Td>
                <Td numeric>{row.equity_after}</Td>
                <Td>{row.status}</Td>
                <Td wrap>{row.skip_reason === null ? EMPTY_VALUE : humanizeCode(row.skip_reason)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </TableScroll>
    </SeriesFrame>
  );
}

export function ZoneEventsTable({ rows }: { rows: readonly ZoneEventProjection[] }) {
  const { shown, remaining, showMore } = useVisibleRows(rows);
  return (
    <SeriesFrame
      title="Zone events"
      total={rows.length}
      shownCount={shown.length}
      remaining={remaining}
      onShowMore={showMore}
      emptyTitle="No zone events"
      emptyBody="This run recorded no zone transitions."
    >
      <TableScroll label="Zone events">
        <Table caption="Zone boundary transitions in global event order">
          <thead>
            <tr>
              <Th numeric>Seq</Th>
              <Th>Date</Th>
              <Th>Event</Th>
              <Th numeric>Price</Th>
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <tr key={row.id}>
                <Td numeric>{row.event_sequence}</Td>
                <Td>{row.date}</Td>
                <Td wrap>{humanizeCode(row.event_type)}</Td>
                <Td numeric>{row.price}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </TableScroll>
    </SeriesFrame>
  );
}

export function DailyEquityTable({ rows }: { rows: readonly DailyEquityProjection[] }) {
  const { shown, remaining, showMore } = useVisibleRows(rows);
  return (
    <SeriesFrame
      title="Daily equity"
      total={rows.length}
      shownCount={shown.length}
      remaining={remaining}
      onShowMore={showMore}
      emptyTitle="No daily equity"
      emptyBody="This run recorded no daily equity rows."
    >
      <TableScroll label="Daily equity">
        <Table caption="One row per trading day, in date order">
          <thead>
            <tr>
              <Th>Date</Th>
              <Th numeric>Close</Th>
              <Th numeric>Cash</Th>
              <Th numeric>Shares</Th>
              <Th numeric>Equity</Th>
              <Th numeric>Drawdown</Th>
              <Th>Zone at close</Th>
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <tr key={row.id}>
                <Td>{row.date}</Td>
                <Td numeric>{row.close}</Td>
                <Td numeric>{row.cash}</Td>
                <Td numeric>{row.shares}</Td>
                <Td numeric>{row.equity}</Td>
                <Td numeric>{row.drawdown}</Td>
                <Td>{humanizeCode(row.zone_at_close)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </TableScroll>
    </SeriesFrame>
  );
}

export function EventEquityTable({ rows }: { rows: readonly EventEquityProjection[] }) {
  const { shown, remaining, showMore } = useVisibleRows(rows);
  return (
    <SeriesFrame
      title="Event equity"
      total={rows.length}
      shownCount={shown.length}
      remaining={remaining}
      onShowMore={showMore}
      emptyTitle="No event equity"
      emptyBody="This run recorded no per-event equity rows."
    >
      <TableScroll label="Event equity">
        <Table caption="Portfolio equity captured at each event, in global event order">
          <thead>
            <tr>
              <Th numeric>Seq</Th>
              <Th>Date</Th>
              <Th numeric>Market price</Th>
              <Th numeric>Cash</Th>
              <Th numeric>Shares</Th>
              <Th numeric>Equity</Th>
            </tr>
          </thead>
          <tbody>
            {shown.map((row) => (
              <tr key={row.id}>
                <Td numeric>{row.event_sequence}</Td>
                <Td>{row.date}</Td>
                <Td numeric>{row.market_price}</Td>
                <Td numeric>{row.cash}</Td>
                <Td numeric>{row.shares}</Td>
                <Td numeric>{row.equity}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </TableScroll>
    </SeriesFrame>
  );
}
