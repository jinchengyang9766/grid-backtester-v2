/**
 * Backtest API functions (SPEC Section 25.3).
 *
 * Only creation and single-run detail exist in this task — history, compare,
 * rerun, duplicate, and export clients belong to later tasks.
 */

import { apiPostJson, apiRequest } from "./client";
import type {
  BacktestCreateRequest,
  BacktestCreateResponse,
  BacktestDetailResponse,
} from "./backtest-types";

/**
 * Execute one backtest synchronously.
 *
 * The request carries exactly `dataset_id`, optional `name`, and
 * `configuration` — the backend forbids extra fields, and status,
 * result_metrics, and the result series are all server-owned.
 *
 * A 201 whose `status` is `FAILED` is a success at the HTTP level: the run
 * row was created, it simply did not complete. It is never retried.
 */
export function createBacktest(
  request: BacktestCreateRequest,
  signal?: AbortSignal,
): Promise<BacktestCreateResponse> {
  return apiPostJson<BacktestCreateResponse>("/api/backtests", request, { signal });
}

/**
 * One owned run's detail.
 *
 * No `include` parameter is sent, so the trades/zone-events/daily-equity/
 * event-equity series are omitted entirely — this task shows only the handoff
 * summary, and the result dashboard arrives later.
 */
export function getBacktest(
  backtestId: number,
  options: { signal?: AbortSignal } = {},
): Promise<BacktestDetailResponse> {
  return apiRequest<BacktestDetailResponse>(`/api/backtests/${backtestId}`, {
    method: "GET",
    signal: options.signal,
  });
}
