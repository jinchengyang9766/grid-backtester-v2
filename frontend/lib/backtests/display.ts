/**
 * Presentation helpers for strategy configuration and run results.
 *
 * Formatting only. Nothing here computes a metric, projects an outcome, or
 * turns a stored decimal string into a number.
 */

import type { OhlcPathMode, ValueMode } from "@/lib/api/backtest-types";
import { decimalTimesHundred, trimTrailingZeros } from "./decimal-string";
import type { ValueFormState } from "./configuration-state";

export const PATH_MODE_LABELS: Record<OhlcPathMode, string> = {
  AUTO: "Automatic (choose per bar)",
  HIGH_FIRST: "High first, then low",
  LOW_FIRST: "Low first, then high",
};

export const PATH_MODE_HINTS: Record<OhlcPathMode, string> = {
  AUTO:
    "The engine picks the intraday order for each bar from that bar's own open and close.",
  HIGH_FIRST: "Assume every bar reaches its high before its low.",
  LOW_FIRST: "Assume every bar reaches its low before its high.",
};

export const VALUE_MODE_LABELS: Record<ValueMode, string> = {
  FIXED: "Fixed amount",
  PERCENT: "Percent of baseline",
};

/**
 * Render a mode+value pair. For PERCENT the exact stored string is kept and a
 * readable percentage is added alongside; the percentage is a digit shift, not
 * a float multiplication.
 */
export function valueLabel(block: ValueFormState): string {
  const value = block.value.trim();
  if (value === "") return "—";
  if (block.mode === "PERCENT") {
    const percent = decimalTimesHundred(value);
    return percent === null ? value : `${value} (${trimTrailingZeros(percent)}%)`;
  }
  return value;
}

/** A rate stored as a decimal fraction, shown with its percentage equivalent. */
export function rateLabel(value: string): string {
  const trimmed = value.trim();
  if (trimmed === "") return "—";
  const percent = decimalTimesHundred(trimmed);
  return percent === null ? trimmed : `${trimmed} (${trimTrailingZeros(percent)}%)`;
}

export function statusLabel(status: string): string {
  switch (status) {
    case "COMPLETED":
      return "Completed";
    case "FAILED":
      return "Failed";
    case "RUNNING":
      return "Running";
    case "PENDING":
      return "Pending";
    default:
      return status;
  }
}

/**
 * Pull a small set of headline figures out of the stored `result_metrics`
 * document, without recomputing anything. Returns the values exactly as the
 * backend stored them (plain decimal strings).
 */
export interface HeadlineMetric {
  label: string;
  value: string;
}

function readString(source: unknown, ...path: string[]): string | null {
  let current: unknown = source;
  for (const key of path) {
    if (typeof current !== "object" || current === null) return null;
    current = (current as Record<string, unknown>)[key];
  }
  if (typeof current === "string") return current;
  if (typeof current === "number") return String(current);
  return null;
}

export function headlineMetrics(
  resultMetrics: Record<string, unknown> | null,
): HeadlineMetric[] {
  if (resultMetrics === null) return [];
  const entries: [string, string[]][] = [
    ["Initial equity", ["metrics", "strategy", "initial_equity"]],
    ["Final equity", ["metrics", "strategy", "final_equity"]],
    ["Net profit", ["metrics", "strategy", "net_profit"]],
    ["Executed trades", ["metrics", "trade_costs", "executed_trades"]],
    ["Skipped trades", ["metrics", "trade_costs", "skipped_trades"]],
    ["Total commission", ["metrics", "trade_costs", "total_commission"]],
  ];
  const found: HeadlineMetric[] = [];
  for (const [label, path] of entries) {
    const value = readString(resultMetrics, ...path);
    if (value !== null) found.push({ label, value });
  }
  return found;
}
