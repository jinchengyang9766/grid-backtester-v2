/**
 * Editable strategy-configuration state.
 *
 * Every numeric field is held as the exact string the user typed, so nothing
 * is reinterpreted between keystroke and request body. Serialization to the
 * backend shape is a pure function of this state.
 *
 * Slippage keeps both the shared and the separate values in UI state so
 * toggling the mode does not discard what was already entered — but the
 * serialized object contains only the active shape the backend accepts.
 */

import type {
  BacktestConfigurationInput,
  CommissionInput,
  OhlcPathMode,
  SlippageInput,
  ValueInput,
  ValueMode,
} from "@/lib/api/backtest-types";

export interface ValueFormState {
  mode: ValueMode;
  value: string;
}

export interface CommissionFormState {
  rate_enabled: boolean;
  rate: string;
  minimum_enabled: boolean;
  minimum: string;
  fixed_enabled: boolean;
  fixed: string;
}

export interface SlippageFormState {
  shared: boolean;
  /** Used when `shared` is true. */
  sharedValue: ValueFormState;
  /** Used when `shared` is false. */
  buy: ValueFormState;
  sell: ValueFormState;
}

export interface ConfigurationFormState {
  initial_cash: string;
  initial_shares: string;
  lot_size: string;
  trade_lots: string;
  /** Blank means "use the dataset's first close" and serializes to null. */
  baseline: string;
  a_distance: ValueFormState;
  c_distance: ValueFormState;
  grid_step: ValueFormState;
  tick_size_enabled: boolean;
  tick_size_value: string;
  ohlc_path_mode: OhlcPathMode;
  buy_commission: CommissionFormState;
  sell_commission: CommissionFormState;
  slippage: SlippageFormState;
  risk_free_rate_annual: string;
}

/** Deep clone, so copying or resetting never shares nested objects. */
export function cloneConfiguration(state: ConfigurationFormState): ConfigurationFormState {
  return {
    ...state,
    a_distance: { ...state.a_distance },
    c_distance: { ...state.c_distance },
    grid_step: { ...state.grid_step },
    buy_commission: { ...state.buy_commission },
    sell_commission: { ...state.sell_commission },
    slippage: {
      shared: state.slippage.shared,
      sharedValue: { ...state.slippage.sharedValue },
      buy: { ...state.slippage.buy },
      sell: { ...state.slippage.sell },
    },
  };
}

export function cloneCommission(commission: CommissionFormState): CommissionFormState {
  return { ...commission };
}

function serializeValue(state: ValueFormState): ValueInput {
  return { mode: state.mode, value: state.value };
}

function serializeCommission(state: CommissionFormState): CommissionInput {
  // Disabled components still serialize their value: the schema requires all
  // six fields, and the engine reads the *_enabled flags to decide what applies.
  return {
    rate_enabled: state.rate_enabled,
    rate: state.rate,
    minimum_enabled: state.minimum_enabled,
    minimum: state.minimum,
    fixed_enabled: state.fixed_enabled,
    fixed: state.fixed,
  };
}

function serializeSlippage(state: SlippageFormState): SlippageInput {
  // Exactly one representation — the backend rejects a mixed object.
  if (state.shared) {
    return {
      shared: true,
      mode: state.sharedValue.mode,
      value: state.sharedValue.value,
    };
  }
  return {
    shared: false,
    buy: serializeValue(state.buy),
    sell: serializeValue(state.sell),
  };
}

/**
 * Build the request configuration.
 *
 * `dataMode` decides the path mode: CLOSE_ONLY datasets have no intraday
 * high/low, so null is sent rather than pretending a path was reconstructed.
 * (The backend canonicalizes it to null regardless.)
 */
export function serializeConfiguration(
  state: ConfigurationFormState,
  dataMode: string,
): BacktestConfigurationInput {
  const trimmedBaseline = state.baseline.trim();
  return {
    initial_cash: state.initial_cash,
    // Integer fields travel as digit strings too. Pydantic coerces them to
    // `int` losslessly, whereas converting here would cap precision at 2**53
    // and reintroduce the float path this module exists to avoid.
    initial_shares: state.initial_shares,
    lot_size: state.lot_size,
    trade_lots: state.trade_lots,
    baseline: trimmedBaseline === "" ? null : trimmedBaseline,
    a_distance: serializeValue(state.a_distance),
    c_distance: serializeValue(state.c_distance),
    grid_step: serializeValue(state.grid_step),
    tick_size: {
      enabled: state.tick_size_enabled,
      value: state.tick_size_enabled ? state.tick_size_value : null,
    },
    ohlc_path_mode: dataMode === "OHLCV" ? state.ohlc_path_mode : null,
    buy_commission: serializeCommission(state.buy_commission),
    sell_commission: serializeCommission(state.sell_commission),
    slippage: serializeSlippage(state.slippage),
    risk_free_rate_annual: state.risk_free_rate_annual,
  };
}
