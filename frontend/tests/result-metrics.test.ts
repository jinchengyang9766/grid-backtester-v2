import { describe, expect, it } from "vitest";

import {
  chartRange,
  seriesFrom,
  tickIndices,
  toCoordinate,
} from "@/lib/backtests/chart-data";
import { configurationToFormState } from "@/lib/backtests/configuration-overrides";
import {
  additionalRows,
  benchmarkPoints,
  benchmarkSections,
  costSection,
  flattenMetrics,
  gridLevels,
  headlineRows,
  readScalar,
  strategySection,
  zoneSection,
} from "@/lib/backtests/metrics";

const METRICS = {
  initial_equity: "106580.00000000",
  baseline: "0.63900000",
  a_lower: "0.57900000",
  a_upper: "0.69900000",
  c_lower: "0.51900000",
  c_upper: "0.75900000",
  grid_step: "0.01",
  grid_levels: ["0.57900000", "0.63900000", "0.69900000"],
  metrics: {
    strategy: {
      initial_equity: "106580.00000000",
      final_equity: "107771.70000000",
      net_profit: "1191.70000000",
      total_return: "0.011181272283730531056483393",
      annualized_return: "0.006709867855762830722388486",
      maximum_drawdown: "-0.0125574249718591970490891340",
      sharpe_ratio: "0.5301681561862160237276256059",
    },
    trade_costs: {
      total_commission: "665",
      total_slippage_cost: "13.300",
      executed_trades: 133,
      skipped_trades: 0,
      buy_count: 64,
      sell_count: 69,
    },
    zones: {
      days_closed_in_a_zone: 184,
      days_closed_in_c_zone: 62,
      days_closed_outside_c: 174,
      zone_event_counts: { ENTER_C_ZONE: 17, EXIT_C_ZONE: 16 },
    },
    first_return: { equity: "106480.800", days: 0 },
    benchmark1: { final_equity: "108470.00000000", total_return: "0.017733158" },
    benchmark2: { final_equity: "136940.82868000", total_return: "0.284864221" },
    benchmark2_day_one_commission: "29.9713200",
    benchmark2_day_one_slippage_cost: "151.600",
  },
  benchmark1: {
    points: [
      { date: "2024-07-23", close: "0.639", cash: "100000", shares: 10000, equity: "106390.0" },
      { date: "2024-07-24", close: "0.641", cash: "100000", shares: 10000, equity: "106500.0" },
    ],
    day_one_purchase: null,
  },
  benchmark2: {
    points: [
      { date: "2024-07-23", close: "0.639", cash: "65.62", shares: 161600, equity: "103328.0" },
    ],
    day_one_purchase: { reference_price: "0.658", lots: 1516 },
  },
  final_state: { cash: "99725.200", shares: 9500, zone_state: "OUTSIDE_C" },
};

describe("reading stored metrics", () => {
  it("returns values exactly as stored, never rounded", () => {
    const rows = strategySection(METRICS).rows;
    const byLabel = new Map(rows.map((row) => [row.label, row.value]));
    expect(byLabel.get("Final equity")).toBe("107771.70000000");
    expect(byLabel.get("Total return")).toBe("0.011181272283730531056483393");
    expect(byLabel.get("Maximum drawdown")).toBe("-0.0125574249718591970490891340");
  });

  it("marks ratio metrics so a percentage can be added losslessly", () => {
    const rows = strategySection(METRICS).rows;
    const totalReturn = rows.find((row) => row.label === "Total return");
    expect(totalReturn?.ratio).toBe(true);
    const sharpe = rows.find((row) => row.label === "Sharpe ratio");
    expect(sharpe?.ratio).toBe(false);
  });

  it("returns null for a metric the document does not contain", () => {
    expect(readScalar(METRICS, "metrics", "strategy", "volatility")).toBeNull();
    expect(readScalar(null, "metrics", "strategy", "final_equity")).toBeNull();
  });

  it("produces empty headline rows for a null document", () => {
    expect(headlineRows(null)).toEqual([]);
  });

  it("reads counts and zone events without recomputation", () => {
    const costs = new Map(costSection(METRICS).rows.map((row) => [row.label, row.value]));
    expect(costs.get("Executed trades")).toBe("133");
    expect(costs.get("Buy count")).toBe("64");
    expect(costs.get("Sell count")).toBe("69");
    expect(costs.get("Total commission")).toBe("665");

    const zones = zoneSection(METRICS).rows.map((row) => row.label);
    expect(zones).toContain("Zone event: ENTER_C_ZONE");
  });

  it("reads both benchmark summaries from the stored metrics block", () => {
    const [first, second] = benchmarkSections(METRICS);
    expect(first.rows.find((row) => row.label.includes("Final equity"))?.value).toBe(
      "108470.00000000",
    );
    expect(second.rows.find((row) => row.label.includes("Final equity"))?.value).toBe(
      "136940.82868000",
    );
  });

  it("reads persisted benchmark point series verbatim", () => {
    const points = benchmarkPoints(METRICS, "benchmark1");
    expect(points).toHaveLength(2);
    expect(points[0]).toMatchObject({ date: "2024-07-23", equity: "106390.0" });
    expect(benchmarkPoints(METRICS, "benchmark2")).toHaveLength(1);
    expect(benchmarkPoints(null, "benchmark1")).toEqual([]);
  });

  it("reads persisted grid levels and never invents any", () => {
    expect(gridLevels(METRICS)).toEqual(["0.57900000", "0.63900000", "0.69900000"]);
    expect(gridLevels({})).toEqual([]);
    expect(gridLevels(null)).toEqual([]);
  });

  it("surfaces unknown scalar keys in a labelled fallback", () => {
    const rows = additionalRows({ ...METRICS, future_metric: "42" });
    expect(rows).toContainEqual({ label: "future_metric", value: "42" });
    // Known keys are not duplicated into the fallback.
    expect(rows.map((row) => row.label)).not.toContain("baseline");
  });
});

describe("flattening for comparison", () => {
  it("produces deterministic dotted paths", () => {
    const flat = flattenMetrics(METRICS);
    expect(flat.get("metrics.strategy.final_equity")).toBe("107771.70000000");
    expect(flat.get("metrics.trade_costs.executed_trades")).toBe("133");
    expect(flat.get("baseline")).toBe("0.63900000");
  });

  it("summarizes long arrays by length instead of expanding them", () => {
    const flat = flattenMetrics(METRICS);
    expect(flat.get("benchmark1.points.length")).toBe("2");
    expect(flat.get("grid_levels.length")).toBe("3");
  });

  it("returns an empty map for null metrics", () => {
    expect(flattenMetrics(null).size).toBe(0);
  });

  it("is stable across repeated calls", () => {
    expect([...flattenMetrics(METRICS).keys()]).toEqual([...flattenMetrics(METRICS).keys()]);
  });
});

describe("chart coordinate adapter", () => {
  it("converts fixed-point strings and rejects anything else", () => {
    expect(toCoordinate("107771.70000000")).toBeCloseTo(107771.7);
    expect(toCoordinate("-0.0125")).toBeCloseTo(-0.0125);
    expect(toCoordinate("1e5")).toBeNull();
    expect(toCoordinate("abc")).toBeNull();
    expect(toCoordinate("")).toBeNull();
  });

  it("keeps the original string beside each coordinate", () => {
    const series = seriesFrom([{ v: "1.50", d: "2024-01-01" }], {
      key: "s",
      label: "S",
      color: "#000",
      value: (row) => row.v,
      label_: (row) => row.d,
    });
    expect(series.points[0].source).toBe("1.50");
    expect(series.points[0].value).toBeCloseTo(1.5);
  });

  it("skips unusable values rather than poisoning the axis", () => {
    const series = seriesFrom([{ v: "1" }, { v: "oops" }, { v: "3" }], {
      key: "s",
      label: "S",
      color: "#000",
      value: (row) => row.v,
      label_: () => "",
    });
    expect(series.points).toHaveLength(2);
  });

  it("pads a flat range so scaling never divides by zero", () => {
    const flat = seriesFrom([{ v: "5" }, { v: "5" }], {
      key: "s",
      label: "S",
      color: "#000",
      value: (row) => row.v,
      label_: () => "",
    });
    const range = chartRange([flat]);
    expect(range).not.toBeNull();
    expect(range!.max).toBeGreaterThan(range!.min);
  });

  it("handles an all-zero series without dividing by zero", () => {
    const zeros = seriesFrom([{ v: "0" }, { v: "0" }], {
      key: "s",
      label: "S",
      color: "#000",
      value: (row) => row.v,
      label_: () => "",
    });
    const range = chartRange([zeros]);
    expect(range!.max).toBeGreaterThan(range!.min);
  });

  it("preserves negative values in the range", () => {
    const negatives = seriesFrom([{ v: "-0.05" }, { v: "0" }], {
      key: "s",
      label: "S",
      color: "#000",
      value: (row) => row.v,
      label_: () => "",
    });
    const range = chartRange([negatives], [0]);
    expect(range!.min).toBeLessThan(0);
  });

  it("returns null when there is nothing to plot", () => {
    expect(chartRange([])).toBeNull();
  });

  it("spaces axis ticks safely for any series length", () => {
    expect(tickIndices(0)).toEqual([]);
    expect(tickIndices(1)).toEqual([0]);
    expect(tickIndices(2)).toEqual([0, 1]);
    expect(tickIndices(420).length).toBeLessThanOrEqual(5);
    expect(tickIndices(420)[0]).toBe(0);
    expect(tickIndices(420).at(-1)).toBe(419);
  });
});

describe("configuration round trip", () => {
  const STORED = {
    initial_cash: "100000",
    initial_shares: 10000,
    lot_size: 100,
    trade_lots: 1,
    baseline: null,
    a_distance: { mode: "FIXED", value: "0.06" },
    c_distance: { mode: "FIXED", value: "0.12" },
    grid_step: { mode: "FIXED", value: "0.01" },
    tick_size: { enabled: true, value: "0.001" },
    ohlc_path_mode: "AUTO",
    buy_commission: {
      rate_enabled: true,
      rate: "0.0003",
      minimum_enabled: true,
      minimum: "5",
      fixed_enabled: false,
      fixed: "0",
    },
    sell_commission: {
      rate_enabled: true,
      rate: "0.0003",
      minimum_enabled: true,
      minimum: "5",
      fixed_enabled: false,
      fixed: "0",
    },
    slippage: { shared: true, mode: "FIXED", value: "0.001", buy: null, sell: null },
    risk_free_rate_annual: "0",
  };

  it("restores every field with its exact stored string", () => {
    const form = configurationToFormState(STORED);
    expect(form.initial_cash).toBe("100000");
    expect(form.initial_shares).toBe("10000");
    expect(form.a_distance).toEqual({ mode: "FIXED", value: "0.06" });
    expect(form.tick_size_enabled).toBe(true);
    expect(form.tick_size_value).toBe("0.001");
    expect(form.ohlc_path_mode).toBe("AUTO");
    expect(form.risk_free_rate_annual).toBe("0");
  });

  it("shows a null baseline as blank", () => {
    expect(configurationToFormState(STORED).baseline).toBe("");
  });

  it("restores shared slippage", () => {
    const form = configurationToFormState(STORED);
    expect(form.slippage.shared).toBe(true);
    expect(form.slippage.sharedValue).toEqual({ mode: "FIXED", value: "0.001" });
  });

  it("restores separate slippage", () => {
    const form = configurationToFormState({
      ...STORED,
      slippage: {
        shared: false,
        mode: null,
        value: null,
        buy: { mode: "PERCENT", value: "0.002" },
        sell: { mode: "FIXED", value: "0.003" },
      },
    });
    expect(form.slippage.shared).toBe(false);
    expect(form.slippage.buy).toEqual({ mode: "PERCENT", value: "0.002" });
    expect(form.slippage.sell).toEqual({ mode: "FIXED", value: "0.003" });
  });

  it("falls back to defaults for an incomplete document", () => {
    const form = configurationToFormState({});
    expect(form.initial_cash).toBe("100000.00");
    expect(form.a_distance.mode).toBe("PERCENT");
  });
});
