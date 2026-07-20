/**
 * Convert a stored canonical configuration back into editable form state,
 * so "duplicate" can start from exactly what the source run executed.
 *
 * Every decimal arrives as a string and stays one; nothing is parsed or
 * re-formatted. Unknown or missing values fall back to the form defaults
 * rather than guessing, so an older stored document still opens cleanly.
 */

import type { OhlcPathMode, ValueMode } from "@/lib/api/backtest-types";
import type {
  CommissionFormState,
  ConfigurationFormState,
  ValueFormState,
} from "./configuration-state";
import { defaultConfiguration } from "./defaults";
import { readNode } from "./metrics";

function text(source: unknown, fallback: string): string {
  if (typeof source === "string") return source;
  if (typeof source === "number") return String(source);
  return fallback;
}

function mode(source: unknown, fallback: ValueMode): ValueMode {
  return source === "FIXED" || source === "PERCENT" ? source : fallback;
}

function flag(source: unknown, fallback: boolean): boolean {
  return typeof source === "boolean" ? source : fallback;
}

function valueBlock(source: unknown, fallback: ValueFormState): ValueFormState {
  return {
    mode: mode(readNode(source, "mode"), fallback.mode),
    value: text(readNode(source, "value"), fallback.value),
  };
}

function commission(source: unknown, fallback: CommissionFormState): CommissionFormState {
  return {
    rate_enabled: flag(readNode(source, "rate_enabled"), fallback.rate_enabled),
    rate: text(readNode(source, "rate"), fallback.rate),
    minimum_enabled: flag(readNode(source, "minimum_enabled"), fallback.minimum_enabled),
    minimum: text(readNode(source, "minimum"), fallback.minimum),
    fixed_enabled: flag(readNode(source, "fixed_enabled"), fallback.fixed_enabled),
    fixed: text(readNode(source, "fixed"), fallback.fixed),
  };
}

export function configurationToFormState(
  configuration: Record<string, unknown>,
): ConfigurationFormState {
  const fallback = defaultConfiguration();
  const storedBaseline = readNode(configuration, "baseline");
  const tickValue = readNode(configuration, "tick_size", "value");
  const pathMode = readNode(configuration, "ohlc_path_mode");
  const slippage = readNode(configuration, "slippage");
  const shared = flag(readNode(slippage, "shared"), fallback.slippage.shared);

  return {
    initial_cash: text(readNode(configuration, "initial_cash"), fallback.initial_cash),
    initial_shares: text(readNode(configuration, "initial_shares"), fallback.initial_shares),
    lot_size: text(readNode(configuration, "lot_size"), fallback.lot_size),
    trade_lots: text(readNode(configuration, "trade_lots"), fallback.trade_lots),
    // A stored null baseline means "use the first close", shown as blank.
    baseline: storedBaseline === null || storedBaseline === undefined ? "" : text(storedBaseline, ""),
    a_distance: valueBlock(readNode(configuration, "a_distance"), fallback.a_distance),
    c_distance: valueBlock(readNode(configuration, "c_distance"), fallback.c_distance),
    grid_step: valueBlock(readNode(configuration, "grid_step"), fallback.grid_step),
    tick_size_enabled: flag(
      readNode(configuration, "tick_size", "enabled"),
      fallback.tick_size_enabled,
    ),
    tick_size_value:
      tickValue === null || tickValue === undefined ? "" : text(tickValue, ""),
    ohlc_path_mode:
      pathMode === "AUTO" || pathMode === "HIGH_FIRST" || pathMode === "LOW_FIRST"
        ? (pathMode as OhlcPathMode)
        : fallback.ohlc_path_mode,
    buy_commission: commission(
      readNode(configuration, "buy_commission"),
      fallback.buy_commission,
    ),
    sell_commission: commission(
      readNode(configuration, "sell_commission"),
      fallback.sell_commission,
    ),
    slippage: {
      shared,
      // Both shapes are kept so toggling in the form loses nothing; only the
      // active one is serialized.
      sharedValue: shared
        ? valueBlock(slippage, fallback.slippage.sharedValue)
        : fallback.slippage.sharedValue,
      buy: valueBlock(readNode(slippage, "buy"), fallback.slippage.buy),
      sell: valueBlock(readNode(slippage, "sell"), fallback.slippage.sell),
    },
    risk_free_rate_annual: text(
      readNode(configuration, "risk_free_rate_annual"),
      fallback.risk_free_rate_annual,
    ),
  };
}
