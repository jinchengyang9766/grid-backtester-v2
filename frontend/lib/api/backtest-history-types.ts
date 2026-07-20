/**
 * History, detail-series, and comparison contracts (SPEC Sections 25.3, 30).
 *
 * Mirrors the checked-in Pydantic schemas in
 * `backend/app/api/schemas/backtests.py`. Every projection value that is a
 * Decimal on the backend arrives as a plain fixed-point string and stays a
 * string here.
 */

import type { BacktestDetailResponse, BacktestStatus } from "./backtest-types";

/** The only include tokens `GET /api/backtests/{id}` accepts. */
export const BACKTEST_INCLUDES = [
  "trades",
  "zone_events",
  "daily_equity",
  "event_equity",
] as const;

export type BacktestInclude = (typeof BACKTEST_INCLUDES)[number];

/** One `GET /api/backtests` row. No configuration, no series, no user_id. */
export interface BacktestListItem {
  id: number;
  dataset_id: number;
  dataset_name: string;
  name: string;
  status: string;
  start_date: string;
  end_date: string;
  ohlc_path_mode: string | null;
  created_at: string;
  completed_at: string | null;
  error_message: string | null;
  result_metrics: Record<string, unknown> | null;
}

export interface BacktestListResponse {
  items: BacktestListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface BacktestListQuery {
  search?: string;
  dataset_id?: number;
  status?: BacktestStatus;
  limit?: number;
  offset?: number;
}

export interface TradeProjection {
  id: number;
  date: string;
  event_sequence: number;
  side: string;
  grid_price: string;
  execution_price: string | null;
  shares: number;
  notional: string | null;
  commission: string | null;
  slippage_cost: string | null;
  cash_after: string;
  shares_after: number;
  equity_after: string;
  status: string;
  skip_reason: string | null;
}

export interface ZoneEventProjection {
  id: number;
  date: string;
  event_sequence: number;
  event_type: string;
  price: string;
}

export interface DailyEquityProjection {
  id: number;
  date: string;
  close: string;
  cash: string;
  shares: number;
  equity: string;
  drawdown: string;
  zone_at_close: string;
}

export interface EventEquityProjection {
  id: number;
  date: string;
  event_sequence: number;
  market_price: string;
  cash: string;
  shares: number;
  equity: string;
}

/**
 * Detail plus the optional series.
 *
 * The route uses `response_model_exclude_unset`, so a series key is absent
 * unless it was requested — hence the optional properties.
 */
export interface BacktestDetailWithSeries extends BacktestDetailResponse {
  trades?: TradeProjection[];
  zone_events?: ZoneEventProjection[];
  daily_equity?: DailyEquityProjection[];
  event_equity?: EventEquityProjection[];
}

/** `POST /api/backtests/compare` → 200, runs in requested order. */
export interface BacktestCompareRun {
  id: number;
  name: string;
  result_metrics: Record<string, unknown> | null;
}

export interface BacktestCompareResponse {
  runs: BacktestCompareRun[];
}

export const BACKTEST_NOT_FOUND = "BACKTEST_NOT_FOUND";
export const IMMUTABLE_FIELD = "IMMUTABLE_FIELD";
