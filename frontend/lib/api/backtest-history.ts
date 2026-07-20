/**
 * History, detail, and lifecycle API functions (SPEC Sections 25.3, 30).
 *
 * Export endpoints are deliberately absent — download controls belong to a
 * later task.
 */

import { apiPostJson, apiRequest } from "./client";
import type { BacktestCreateResponse } from "./backtest-types";
import type {
  BacktestCompareResponse,
  BacktestDetailWithSeries,
  BacktestInclude,
  BacktestListQuery,
  BacktestListResponse,
} from "./backtest-history-types";
import type { BacktestConfigurationInput } from "./backtest-types";

/** Only non-empty filters are sent, so a blank search is simply omitted. */
function listSearchParams(query: BacktestListQuery): string {
  const params = new URLSearchParams();
  const search = query.search?.trim();
  if (search) params.set("search", search);
  if (query.dataset_id !== undefined) params.set("dataset_id", String(query.dataset_id));
  if (query.status !== undefined) params.set("status", query.status);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const text = params.toString();
  return text === "" ? "" : `?${text}`;
}

export function listBacktests(
  query: BacktestListQuery = {},
  signal?: AbortSignal,
): Promise<BacktestListResponse> {
  return apiRequest<BacktestListResponse>(`/api/backtests${listSearchParams(query)}`, {
    method: "GET",
    signal,
  });
}

/** Series arrive only for the include tokens actually requested. */
export function getBacktestDetail(
  backtestId: number,
  options: { include?: BacktestInclude[]; signal?: AbortSignal } = {},
): Promise<BacktestDetailWithSeries> {
  const include = options.include ?? [];
  const suffix =
    include.length === 0 ? "" : `?${new URLSearchParams({ include: include.join(",") })}`;
  return apiRequest<BacktestDetailWithSeries>(`/api/backtests/${backtestId}${suffix}`, {
    method: "GET",
    signal: options.signal,
  });
}

/** Rename only: any other key is a deliberate 422 IMMUTABLE_FIELD. */
export function renameBacktest(
  backtestId: number,
  name: string,
  signal?: AbortSignal,
): Promise<BacktestDetailWithSeries> {
  return apiRequest<BacktestDetailWithSeries>(`/api/backtests/${backtestId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
    signal,
  });
}

export function deleteBacktest(backtestId: number, signal?: AbortSignal): Promise<void> {
  return apiRequest<void>(`/api/backtests/${backtestId}`, { method: "DELETE", signal });
}

/**
 * Re-execute the stored configuration against the dataset's current bars,
 * creating a new run. Synchronous, so the response is already COMPLETED or
 * FAILED. Takes no request body.
 */
export function rerunBacktest(
  backtestId: number,
  signal?: AbortSignal,
): Promise<BacktestCreateResponse> {
  return apiRequest<BacktestCreateResponse>(`/api/backtests/${backtestId}/rerun`, {
    method: "POST",
    signal,
  });
}

/**
 * Copy the source configuration, apply overrides, and execute immediately.
 *
 * The full edited configuration is sent as the override document: the
 * backend's override schema accepts every field and validates the merged
 * result through the same full-configuration model, so a hand-computed
 * minimal diff would add risk for no benefit.
 */
export function duplicateBacktest(
  backtestId: number,
  configurationOverrides: BacktestConfigurationInput,
  signal?: AbortSignal,
): Promise<BacktestCreateResponse> {
  return apiPostJson<BacktestCreateResponse>(
    `/api/backtests/${backtestId}/duplicate`,
    { configuration_overrides: configurationOverrides },
    { signal },
  );
}

/** All-or-nothing; the response preserves the requested id order. */
export function compareBacktests(
  backtestIds: number[],
  signal?: AbortSignal,
): Promise<BacktestCompareResponse> {
  return apiPostJson<BacktestCompareResponse>(
    "/api/backtests/compare",
    { backtest_ids: backtestIds },
    { signal },
  );
}
