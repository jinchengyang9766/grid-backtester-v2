/**
 * Fixed-point decimal strings.
 *
 * Every financial value stays a string from keystroke to request body. It is
 * never routed through `Number`, `parseFloat`, unary `+`, or `toFixed`:
 * binary floating point cannot represent most decimal fractions exactly, so a
 * single conversion would silently alter a price, rate, or cash amount before
 * the backend's Decimal parser ever saw it.
 *
 * Comparison is done on BigInt-scaled integers, which is exact at any
 * magnitude. Nothing here rounds; the backend remains the final parser.
 */

export type DecimalString = string;

/**
 * Ordinary fixed-point only: an optional sign, digits, and at most one
 * decimal point with digits on at least one side. Scientific notation,
 * thousands separators, currency symbols, and whitespace are all rejected.
 */
const FIXED_POINT = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/;

export function isDecimalString(value: string): boolean {
  return FIXED_POINT.test(value);
}

/** Plain integers only, e.g. share counts and lot sizes. */
const INTEGER = /^[+-]?\d+$/;

export function isIntegerString(value: string): boolean {
  return INTEGER.test(value);
}

interface Scaled {
  /** The value as an integer scaled by 10**scale. */
  units: bigint;
  scale: number;
}

/** Exact BigInt representation; null when the text is not fixed-point. */
function scaled(value: string): Scaled | null {
  if (!isDecimalString(value)) return null;

  let text = value;
  let negative = false;
  if (text.startsWith("+")) {
    text = text.slice(1);
  } else if (text.startsWith("-")) {
    negative = true;
    text = text.slice(1);
  }

  const pointIndex = text.indexOf(".");
  const digits =
    pointIndex === -1 ? text : text.slice(0, pointIndex) + text.slice(pointIndex + 1);
  const scale = pointIndex === -1 ? 0 : text.length - pointIndex - 1;

  // "5." and ".5" are accepted by the grammar; "" would not be.
  const units = BigInt(digits === "" ? "0" : digits);
  return { units: negative ? -units : units, scale };
}

/** Re-scale two values to a common exponent so they compare exactly. */
function align(a: Scaled, b: Scaled): [bigint, bigint] {
  const scale = Math.max(a.scale, b.scale);
  const lift = (value: Scaled) => value.units * 10n ** BigInt(scale - value.scale);
  return [lift(a), lift(b)];
}

/**
 * -1, 0, or 1, or null when either side is not a decimal string.
 * `1`, `1.0`, and `1.000` all compare equal.
 */
export function compareDecimals(a: string, b: string): -1 | 0 | 1 | null {
  const left = scaled(a);
  const right = scaled(b);
  if (left === null || right === null) return null;
  const [x, y] = align(left, right);
  if (x < y) return -1;
  if (x > y) return 1;
  return 0;
}

export function decimalsEqual(a: string, b: string): boolean {
  return compareDecimals(a, b) === 0;
}

export function isPositiveDecimal(value: string): boolean {
  const parsed = scaled(value);
  return parsed !== null && parsed.units > 0n;
}

export function isNonNegativeDecimal(value: string): boolean {
  const parsed = scaled(value);
  return parsed !== null && parsed.units >= 0n;
}

export function isNegativeDecimal(value: string): boolean {
  const parsed = scaled(value);
  return parsed !== null && parsed.units < 0n;
}

/** Exact for arbitrarily large integers — no float precision ceiling. */
export function isPositiveInteger(value: string): boolean {
  return isIntegerString(value) && BigInt(value) > 0n;
}

export function isNonNegativeInteger(value: string): boolean {
  return isIntegerString(value) && BigInt(value) >= 0n;
}

/**
 * A decimal string multiplied by 100, for showing a rate as a percentage.
 * Implemented as a digit shift so no float ever appears; returns null when
 * the input is not fixed-point.
 */
export function decimalTimesHundred(value: string): string | null {
  const parsed = scaled(value);
  if (parsed === null) return null;

  const negative = parsed.units < 0n;
  const digits = (negative ? -parsed.units : parsed.units).toString();
  const scale = parsed.scale;

  if (scale <= 2) {
    // Shifting left: append zeros for the remaining places.
    const shifted = digits + "0".repeat(2 - scale);
    return (negative ? "-" : "") + stripLeadingZeros(shifted);
  }
  const pointFromRight = scale - 2;
  const padded = digits.padStart(pointFromRight + 1, "0");
  const whole = padded.slice(0, padded.length - pointFromRight);
  const fraction = padded.slice(padded.length - pointFromRight);
  const text = `${stripLeadingZeros(whole)}.${fraction}`;
  return (negative ? "-" : "") + text;
}

function stripLeadingZeros(digits: string): string {
  const trimmed = digits.replace(/^0+/, "");
  return trimmed === "" ? "0" : trimmed;
}

/** Drop trailing fractional zeros for display only; never for submission. */
export function trimTrailingZeros(value: string): string {
  if (!value.includes(".")) return value;
  return value.replace(/\.?0+$/, "") || "0";
}

/**
 * Cut a decimal string to at most `places` fractional digits, by truncation.
 *
 * Pure string surgery — no rounding and no float. Truncating rather than
 * rounding avoids implying a precision the shortened text does not have, and
 * the caller always shows the exact stored value alongside. `truncated` says
 * whether anything was dropped, so the UI can mark the value approximate.
 */
export function truncateDecimal(
  value: string,
  places: number,
): { text: string; truncated: boolean } {
  if (!isDecimalString(value)) return { text: value, truncated: false };
  const pointIndex = value.indexOf(".");
  if (pointIndex === -1) return { text: value, truncated: false };

  const fraction = value.slice(pointIndex + 1);
  if (fraction.length <= places) return { text: value, truncated: false };

  const kept = fraction.slice(0, places);
  const whole = value.slice(0, pointIndex);
  const text = places === 0 ? whole : `${whole}.${kept}`;
  return { text, truncated: true };
}
