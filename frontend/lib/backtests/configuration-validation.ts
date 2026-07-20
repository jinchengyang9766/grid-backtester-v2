/**
 * Client-side configuration validation.
 *
 * This exists for immediate, field-level feedback only. The backend engine
 * remains the authority: it re-checks everything here and additionally
 * enforces rules this module deliberately does not reimplement (grid density,
 * collapse after tick rounding, zero initial equity). Duplicating engine
 * formulas in the browser would risk disagreeing with the real result.
 */

import {
  compareDecimals,
  isDecimalString,
  isNonNegativeDecimal,
  isNonNegativeInteger,
  isPositiveDecimal,
  isPositiveInteger,
} from "./decimal-string";
import type { ConfigurationFormState, ValueFormState } from "./configuration-state";

/** Dotted paths matching the backend's `details.field` hints. */
export type FieldErrors = Record<string, string>;

const MALFORMED =
  "Enter a plain decimal number, for example 0.05 (no commas, symbols, or exponents).";

function checkDecimal(
  errors: FieldErrors,
  path: string,
  value: string,
  rule: "positive" | "non-negative",
  label: string,
): void {
  const trimmed = value.trim();
  if (trimmed === "") {
    errors[path] = `${label} is required.`;
    return;
  }
  if (!isDecimalString(trimmed)) {
    errors[path] = MALFORMED;
    return;
  }
  if (rule === "positive" && !isPositiveDecimal(trimmed)) {
    errors[path] = `${label} must be greater than zero.`;
  } else if (rule === "non-negative" && !isNonNegativeDecimal(trimmed)) {
    errors[path] = `${label} cannot be negative.`;
  }
}

function checkInteger(
  errors: FieldErrors,
  path: string,
  value: string,
  rule: "positive" | "non-negative",
  label: string,
): void {
  const trimmed = value.trim();
  if (trimmed === "") {
    errors[path] = `${label} is required.`;
    return;
  }
  if (rule === "positive") {
    if (!isPositiveInteger(trimmed)) {
      errors[path] = `${label} must be a whole number greater than zero.`;
    }
  } else if (!isNonNegativeInteger(trimmed)) {
    errors[path] = `${label} must be a whole number of zero or more.`;
  }
}

function checkValueBlock(
  errors: FieldErrors,
  path: string,
  block: ValueFormState,
  label: string,
): void {
  checkDecimal(errors, `${path}.value`, block.value, "positive", label);
}

function checkCommission(
  errors: FieldErrors,
  path: string,
  commission: ConfigurationFormState["buy_commission"],
  label: string,
): void {
  // Only enabled components are validated: a disabled component's value still
  // serializes but the engine ignores it.
  if (commission.rate_enabled) {
    checkDecimal(errors, `${path}.rate`, commission.rate, "non-negative", `${label} rate`);
  }
  if (commission.minimum_enabled) {
    checkDecimal(
      errors,
      `${path}.minimum`,
      commission.minimum,
      "non-negative",
      `${label} minimum`,
    );
  }
  if (commission.fixed_enabled) {
    checkDecimal(errors, `${path}.fixed`, commission.fixed, "non-negative", `${label} fixed fee`);
  }
}

export interface ValidationResult {
  valid: boolean;
  fieldErrors: FieldErrors;
}

export function validateConfiguration(state: ConfigurationFormState): ValidationResult {
  const errors: FieldErrors = {};

  // Portfolio
  checkDecimal(errors, "configuration.initial_cash", state.initial_cash, "non-negative", "Initial cash");
  checkInteger(
    errors,
    "configuration.initial_shares",
    state.initial_shares,
    "non-negative",
    "Initial shares",
  );
  checkInteger(errors, "configuration.lot_size", state.lot_size, "positive", "Lot size");
  checkInteger(errors, "configuration.trade_lots", state.trade_lots, "positive", "Trade lots");

  // Grid geometry
  const baseline = state.baseline.trim();
  if (baseline !== "") {
    if (!isDecimalString(baseline)) {
      errors["configuration.baseline"] = MALFORMED;
    } else if (!isPositiveDecimal(baseline)) {
      errors["configuration.baseline"] = "Baseline must be greater than zero.";
    }
  }
  checkValueBlock(errors, "configuration.a_distance", state.a_distance, "A distance");
  checkValueBlock(errors, "configuration.c_distance", state.c_distance, "C distance");
  checkValueBlock(errors, "configuration.grid_step", state.grid_step, "Grid step");

  // C must sit outside A. Only comparable when both use the same mode and
  // both parse; the backend re-checks after converting percentages to prices.
  if (
    !errors["configuration.a_distance.value"] &&
    !errors["configuration.c_distance.value"] &&
    state.a_distance.mode === state.c_distance.mode
  ) {
    const ordering = compareDecimals(state.c_distance.value.trim(), state.a_distance.value.trim());
    if (ordering !== null && ordering <= 0) {
      errors["configuration.c_distance"] =
        "C distance must be greater than A distance, so the outer boundary sits beyond the inner zone.";
    }
  }

  // Tick size
  if (state.tick_size_enabled) {
    checkDecimal(
      errors,
      "configuration.tick_size.value",
      state.tick_size_value,
      "positive",
      "Tick size",
    );
  }

  // Fees
  checkCommission(errors, "configuration.buy_commission", state.buy_commission, "Buy commission");
  checkCommission(errors, "configuration.sell_commission", state.sell_commission, "Sell commission");

  // Slippage: only the active shape is validated, matching what is submitted.
  if (state.slippage.shared) {
    checkDecimal(
      errors,
      "configuration.slippage.value",
      state.slippage.sharedValue.value,
      "non-negative",
      "Slippage",
    );
  } else {
    checkDecimal(
      errors,
      "configuration.slippage.buy.value",
      state.slippage.buy.value,
      "non-negative",
      "Buy slippage",
    );
    checkDecimal(
      errors,
      "configuration.slippage.sell.value",
      state.slippage.sell.value,
      "non-negative",
      "Sell slippage",
    );
  }

  // Risk assumptions: may be negative, so only the syntax is checked here.
  const rate = state.risk_free_rate_annual.trim();
  if (rate === "") {
    errors["configuration.risk_free_rate_annual"] = "Risk-free rate is required.";
  } else if (!isDecimalString(rate)) {
    errors["configuration.risk_free_rate_annual"] = MALFORMED;
  }

  return { valid: Object.keys(errors).length === 0, fieldErrors: errors };
}

/**
 * Map a backend 422's `details.field` onto a form field path.
 *
 * The backend hints at paths such as `configuration.c_distance`; those already
 * match this module's keys, so the message is attached directly.
 */
export function backendFieldError(details: unknown): { path: string; reason: string } | null {
  if (typeof details !== "object" || details === null) return null;
  const { field, reason } = details as { field?: unknown; reason?: unknown };
  if (typeof field !== "string") return null;
  return { path: field, reason: typeof reason === "string" ? reason : "" };
}

/** Codes whose message belongs beside the grid-geometry section. */
const GRID_SECTION_CODES = new Set([
  "NON_POSITIVE_BASELINE",
  "NON_POSITIVE_DISTANCE",
  "INVALID_ZONE_CONFIG",
  "NON_POSITIVE_GRID_STEP",
  "GRID_TOO_DENSE",
  "GRID_COLLAPSES_AFTER_TICK_ROUNDING",
]);

export function isGridSectionCode(code: string): boolean {
  return GRID_SECTION_CODES.has(code);
}
