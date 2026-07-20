/**
 * Initial strategy-configuration values.
 *
 * Only three defaults are actually frozen by the backend schema, which gives
 * every other field no default at all:
 *
 *   - `baseline` defaults to null ("use the dataset's first close")
 *   - `tick_size.value` defaults to null
 *   - `ohlc_path_mode` defaults to null
 *
 * The remaining fields are required, so the form has to start somewhere. It
 * starts from SPEC Section 25.3's illustrative request, which is the only
 * complete configuration the specification actually writes down. These are
 * **starting values, not frozen defaults**, and the UI says so.
 *
 * They are deliberately NOT the Task-12 real-file smoke configuration (which
 * uses initial_shares 10000, FIXED distances, and tick size enabled): that
 * combination is tuned to one specific security and would be a poor and
 * misleading starting point for an arbitrary dataset.
 *
 * `ohlc_path_mode` starts at AUTO because the engine *requires* a path mode
 * for an OHLCV dataset; for CLOSE_ONLY it is serialized as null.
 */

import type { ConfigurationFormState } from "./configuration-state";

export const DEFAULT_CONFIGURATION: ConfigurationFormState = {
  initial_cash: "100000.00",
  initial_shares: "0",
  lot_size: "100",
  trade_lots: "1",
  baseline: "",
  a_distance: { mode: "PERCENT", value: "0.05" },
  c_distance: { mode: "PERCENT", value: "0.15" },
  grid_step: { mode: "PERCENT", value: "0.01" },
  tick_size_enabled: false,
  tick_size_value: "",
  ohlc_path_mode: "AUTO",
  buy_commission: {
    rate_enabled: true,
    rate: "0.0003",
    minimum_enabled: true,
    minimum: "5.00",
    fixed_enabled: false,
    fixed: "0",
  },
  sell_commission: {
    rate_enabled: true,
    rate: "0.0003",
    minimum_enabled: true,
    minimum: "5.00",
    fixed_enabled: false,
    fixed: "0",
  },
  slippage: {
    shared: true,
    sharedValue: { mode: "FIXED", value: "0.001" },
    buy: { mode: "FIXED", value: "0.001" },
    sell: { mode: "FIXED", value: "0.001" },
  },
  risk_free_rate_annual: "0.0",
};

/** A fresh deep copy, so the shared constant is never mutated. */
export function defaultConfiguration(): ConfigurationFormState {
  return {
    ...DEFAULT_CONFIGURATION,
    a_distance: { ...DEFAULT_CONFIGURATION.a_distance },
    c_distance: { ...DEFAULT_CONFIGURATION.c_distance },
    grid_step: { ...DEFAULT_CONFIGURATION.grid_step },
    buy_commission: { ...DEFAULT_CONFIGURATION.buy_commission },
    sell_commission: { ...DEFAULT_CONFIGURATION.sell_commission },
    slippage: {
      shared: DEFAULT_CONFIGURATION.slippage.shared,
      sharedValue: { ...DEFAULT_CONFIGURATION.slippage.sharedValue },
      buy: { ...DEFAULT_CONFIGURATION.slippage.buy },
      sell: { ...DEFAULT_CONFIGURATION.slippage.sell },
    },
  };
}
