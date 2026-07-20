import { describe, expect, it } from "vitest";

import {
  compareDecimals,
  decimalTimesHundred,
  decimalsEqual,
  isDecimalString,
  isIntegerString,
  isNegativeDecimal,
  isNonNegativeDecimal,
  isNonNegativeInteger,
  isPositiveDecimal,
  isPositiveInteger,
  trimTrailingZeros,
} from "@/lib/backtests/decimal-string";

describe("decimal syntax", () => {
  it.each([
    "0",
    "5",
    "100000",
    "0.001",
    "107771.70000000",
    "-1",
    "-0.5",
    "+3",
    "5.",
    ".5",
    "0.0000000000000000001",
    "123456789012345678901234567890.123456789",
  ])("accepts %s", (value) => {
    expect(isDecimalString(value)).toBe(true);
  });

  it.each([
    "",
    " ",
    "1e5",
    "1E5",
    "1e-5",
    "1,000",
    "1 000",
    "$5",
    "5%",
    "abc",
    "1.2.3",
    "--1",
    "+-1",
    "NaN",
    "Infinity",
    "-Infinity",
    "0x10",
    "1_000",
    " 1",
    "1 ",
  ])("rejects %s", (value) => {
    expect(isDecimalString(value)).toBe(false);
  });
});

describe("integer syntax", () => {
  it.each(["0", "1", "-4", "+7", "10000", "99999999999999999999999999"])(
    "accepts %s",
    (value) => {
      expect(isIntegerString(value)).toBe(true);
    },
  );

  it.each(["", "1.0", "1.", ".1", "1e3", "1,0", "abc"])("rejects %s", (value) => {
    expect(isIntegerString(value)).toBe(false);
  });
});

describe("sign predicates", () => {
  it("classifies positives, zeros, and negatives exactly", () => {
    expect(isPositiveDecimal("0.0000001")).toBe(true);
    expect(isPositiveDecimal("0")).toBe(false);
    expect(isPositiveDecimal("0.000")).toBe(false);
    expect(isPositiveDecimal("-0.1")).toBe(false);

    expect(isNonNegativeDecimal("0")).toBe(true);
    expect(isNonNegativeDecimal("0.00")).toBe(true);
    expect(isNonNegativeDecimal("-0.00")).toBe(true);
    expect(isNonNegativeDecimal("-0.01")).toBe(false);

    expect(isNegativeDecimal("-0.01")).toBe(true);
    expect(isNegativeDecimal("0")).toBe(false);
  });

  it("classifies integers without a precision ceiling", () => {
    expect(isPositiveInteger("1")).toBe(true);
    expect(isPositiveInteger("0")).toBe(false);
    expect(isPositiveInteger("-1")).toBe(false);
    expect(isNonNegativeInteger("0")).toBe(true);
    expect(isNonNegativeInteger("-1")).toBe(false);

    // Beyond Number.MAX_SAFE_INTEGER: a float round-trip would lose this.
    const huge = "9007199254740993";
    expect(isPositiveInteger(huge)).toBe(true);
    expect(BigInt(huge).toString()).toBe(huge);
  });
});

describe("comparison", () => {
  it("treats different scales of the same value as equal", () => {
    expect(decimalsEqual("1", "1.0")).toBe(true);
    expect(decimalsEqual("1.0", "1.000")).toBe(true);
    expect(decimalsEqual("0", "0.00000")).toBe(true);
    expect(decimalsEqual("-0", "0")).toBe(true);
    expect(decimalsEqual("0.05", "0.050")).toBe(true);
  });

  it("orders values across scales", () => {
    expect(compareDecimals("0.15", "0.05")).toBe(1);
    expect(compareDecimals("0.05", "0.15")).toBe(-1);
    expect(compareDecimals("0.1", "0.10")).toBe(0);
    expect(compareDecimals("-1", "1")).toBe(-1);
    expect(compareDecimals("2", "10")).toBe(-1);
  });

  it("is exact where binary floating point is not", () => {
    // 0.1 + 0.2 !== 0.3 in float; these strings compare exactly.
    expect(compareDecimals("0.30", "0.3")).toBe(0);
    expect(compareDecimals("0.1", "0.2")).toBe(-1);
    // A value beyond double precision still compares correctly.
    expect(compareDecimals("1.00000000000000000001", "1")).toBe(1);
    expect(compareDecimals("9007199254740993", "9007199254740992")).toBe(1);
  });

  it("returns null when either side is not a decimal string", () => {
    expect(compareDecimals("1e3", "1")).toBeNull();
    expect(compareDecimals("1", "abc")).toBeNull();
    expect(decimalsEqual("1", "1,0")).toBe(false);
  });

  it("never rounds", () => {
    expect(decimalsEqual("0.005", "0.01")).toBe(false);
    expect(decimalsEqual("1.4999999999", "1.5")).toBe(false);
  });
});

describe("percentage rendering", () => {
  it("shifts digits instead of multiplying through a float", () => {
    expect(decimalTimesHundred("0.0003")).toBe("0.03");
    expect(decimalTimesHundred("0.05")).toBe("5");
    expect(decimalTimesHundred("0.15")).toBe("15");
    expect(decimalTimesHundred("1")).toBe("100");
    expect(decimalTimesHundred("0")).toBe("0");
    expect(decimalTimesHundred("0.001")).toBe("0.1");
    expect(decimalTimesHundred("-0.02")).toBe("-2");
    expect(decimalTimesHundred("0.000001")).toBe("0.0001");
  });

  it("avoids the float artefact a naive multiply would produce", () => {
    // 0.07 * 100 === 7.000000000000001 in IEEE-754 double arithmetic.
    expect(decimalTimesHundred("0.07")).toBe("7");
    expect(decimalTimesHundred("0.29")).toBe("29");
  });

  it("returns null for non-decimal input", () => {
    expect(decimalTimesHundred("1e2")).toBeNull();
    expect(decimalTimesHundred("abc")).toBeNull();
  });
});

describe("display trimming", () => {
  it("trims only trailing fractional zeros", () => {
    expect(trimTrailingZeros("5.00")).toBe("5");
    expect(trimTrailingZeros("0.100")).toBe("0.1");
    expect(trimTrailingZeros("100")).toBe("100");
    expect(trimTrailingZeros("0.000")).toBe("0");
  });
});

describe("implementation constraints", () => {
  it("uses no float conversion anywhere in the module", async () => {
    const { readFileSync } = await import("node:fs");
    const { join } = await import("node:path");
    const source = readFileSync(
      join(__dirname, "..", "lib", "backtests", "decimal-string.ts"),
      "utf8",
    )
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/(^|[^:])\/\/.*$/gm, "$1");

    expect(source).not.toMatch(/parseFloat/);
    expect(source).not.toMatch(/toFixed/);
    expect(source).not.toMatch(/[^.\w]Number\(/);
    // BigInt is the arithmetic used instead.
    expect(source).toMatch(/BigInt/);
  });
});
