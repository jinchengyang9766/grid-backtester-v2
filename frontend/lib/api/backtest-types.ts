/**
 * Backtest request/response contracts (SPEC Section 25.3).
 *
 * Mirrors the checked-in Pydantic schemas in
 * `backend/app/api/schemas/backtests.py` exactly. Every model there declares
 * `extra="forbid"`, so an unknown field is a 422 — these types therefore list
 * precisely the accepted fields and nothing else.
 *
 * Decimal fields are typed as strings: Pydantic parses `"0.06"` into a
 * `Decimal` losslessly, whereas a JSON number would already have been through
 * binary floating point.
 */

import type { DecimalString } from "@/lib/backtests/decimal-string";

export const VALUE_MODES = ["FIXED", "PERCENT"] as const;
export type ValueMode = (typeof VALUE_MODES)[number];

export const OHLC_PATH_MODES = ["AUTO", "HIGH_FIRST", "LOW_FIRST"] as const;
export type OhlcPathMode = (typeof OHLC_PATH_MODES)[number];

export interface ValueInput {
  mode: ValueMode;
  value: DecimalString;
}

export interface TickSizeInput {
  enabled: boolean;
  value: DecimalString | null;
}

export interface CommissionInput {
  rate_enabled: boolean;
  rate: DecimalString;
  minimum_enabled: boolean;
  minimum: DecimalString;
  fixed_enabled: boolean;
  fixed: DecimalString;
}

export interface SlippageSideInput {
  mode: ValueMode;
  value: DecimalString;
}

/**
 * The backend validator enforces an exclusive shape: shared requires
 * `mode`+`value` and forbids `buy`/`sell`; separate requires `buy`+`sell` and
 * forbids top-level `mode`/`value`.
 */
export interface SlippageInput {
  shared: boolean;
  mode?: ValueMode | null;
  value?: DecimalString | null;
  buy?: SlippageSideInput | null;
  sell?: SlippageSideInput | null;
}

export interface BacktestConfigurationInput {
  initial_cash: DecimalString;
  /**
   * Integer counts, sent as digit strings. The schema types them as `int` and
   * Pydantic coerces losslessly, which keeps arbitrarily large values exact —
   * a JavaScript number would cap at 2**53.
   */
  initial_shares: string;
  lot_size: string;
  trade_lots: string;
  /** Null means "use the dataset's first close" (SPEC Section 7.1). */
  baseline: DecimalString | null;
  a_distance: ValueInput;
  c_distance: ValueInput;
  grid_step: ValueInput;
  tick_size: TickSizeInput;
  /** Required for OHLCV datasets; null for CLOSE_ONLY. */
  ohlc_path_mode: OhlcPathMode | null;
  buy_commission: CommissionInput;
  sell_commission: CommissionInput;
  slippage: SlippageInput;
  risk_free_rate_annual: DecimalString;
}

export interface BacktestCreateRequest {
  dataset_id: number;
  /** Omitted or null lets the backend generate the canonical name. */
  name?: string | null;
  configuration: BacktestConfigurationInput;
}

export const BACKTEST_STATUSES = ["PENDING", "RUNNING", "COMPLETED", "FAILED"] as const;
export type BacktestStatus = (typeof BACKTEST_STATUSES)[number];

/**
 * `POST /api/backtests` → 201.
 *
 * Execution is synchronous, so `status` is already COMPLETED or FAILED — a
 * FAILED run is still a successfully created resource, not a request error.
 */
export interface BacktestCreateResponse {
  id: number;
  status: string;
  name: string;
  created_at: string;
  completed_at: string | null;
  error_message: string | null;
  result_metrics: Record<string, unknown> | null;
}

export interface DatasetSummaryInBacktest {
  id: number;
  name: string;
  source_type: string;
  original_filename: string;
  security_name: string | null;
  security_code: string | null;
  data_mode: string;
  start_date: string;
  end_date: string;
  row_count: number;
}

/**
 * `GET /api/backtests/{id}`.
 *
 * The four series fields are returned only when `?include=` asks for them;
 * this task never does, so they are typed as absent.
 */
export interface BacktestDetailResponse {
  id: number;
  dataset_id: number;
  dataset: DatasetSummaryInBacktest;
  name: string;
  status: string;
  configuration: Record<string, unknown>;
  ohlc_path_mode: string | null;
  start_date: string;
  end_date: string;
  result_metrics: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

/** 422 codes raised by engine configuration validation; no run is created. */
export const CONFIGURATION_ERROR_CODES = [
  "NON_POSITIVE_BASELINE",
  "NON_POSITIVE_DISTANCE",
  "INVALID_ZONE_CONFIG",
  "NON_POSITIVE_GRID_STEP",
  "GRID_TOO_DENSE",
  "GRID_COLLAPSES_AFTER_TICK_ROUNDING",
  "INVALID_LOT_SIZE",
  "INVALID_TRADE_LOTS",
  "NEGATIVE_INITIAL_CASH",
  "NEGATIVE_INITIAL_SHARES",
  "ZERO_INITIAL_EQUITY",
  "NEGATIVE_COMMISSION_COMPONENT",
  "NEGATIVE_SLIPPAGE",
  "NON_POSITIVE_TICK_SIZE",
  "INVALID_RISK_FREE_RATE",
  "VALIDATION_ERROR",
] as const;

export type ConfigurationErrorCode = (typeof CONFIGURATION_ERROR_CODES)[number];

export function isConfigurationErrorCode(code: string): code is ConfigurationErrorCode {
  return (CONFIGURATION_ERROR_CODES as readonly string[]).includes(code);
}
