import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BacktestDetailPage } from "@/components/results/backtest-detail-page";
import { AuthProvider } from "@/lib/auth/auth-context";

const push = vi.fn();
const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace, refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/history/5",
}));

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const AUTH_OK = { id: 1, email: "owner@example.com" };

const DATASET = {
  id: 7,
  name: "农业ETF富国 159825",
  source_type: "TDX_XLS",
  original_filename: "159825.xls",
  security_name: "农业ETF富国",
  security_code: "159825",
  data_mode: "OHLCV",
  start_date: "2024-07-23",
  end_date: "2026-04-17",
  row_count: 420,
};

const CONFIGURATION = {
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
    minimum_enabled: false,
    minimum: "0",
    fixed_enabled: false,
    fixed: "0",
  },
  slippage: { shared: true, mode: "FIXED", value: "0.001", buy: null, sell: null },
  risk_free_rate_annual: "0",
};

const METRICS = {
  baseline: "0.63900000",
  a_lower: "0.57900000",
  a_upper: "0.69900000",
  c_lower: "0.51900000",
  c_upper: "0.75900000",
  grid_step: "0.01",
  grid_levels: ["0.57900000", "0.63900000"],
  metrics: {
    strategy: {
      initial_equity: "106580.00000000",
      final_equity: "107771.70000000",
      net_profit: "1191.70000000",
      total_return: "0.011181272283730531056483393",
      annualized_return: "0.006709867",
      maximum_drawdown: "-0.012557424",
      sharpe_ratio: "0.530168156",
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
      zone_event_counts: { ENTER_C_ZONE: 17 },
    },
    first_return: { equity: "106480.800", days: 0 },
    benchmark1: { final_equity: "108470.00000000" },
    benchmark2: { final_equity: "136940.82868000" },
    benchmark2_day_one_commission: "29.9713200",
    benchmark2_day_one_slippage_cost: "151.600",
  },
  benchmark1: {
    points: [
      { date: "2024-07-23", close: "0.639", cash: "1", shares: 1, equity: "106390.0" },
      { date: "2024-07-24", close: "0.641", cash: "1", shares: 1, equity: "106500.0" },
    ],
    day_one_purchase: null,
  },
  benchmark2: {
    points: [
      { date: "2024-07-23", close: "0.639", cash: "1", shares: 1, equity: "103328.0" },
    ],
    day_one_purchase: { reference_price: "0.65800000", lots: 1516 },
  },
  final_state: { cash: "99725.200", shares: 9500, zone_state: "OUTSIDE_C" },
};

function detail(overrides: Record<string, unknown> = {}) {
  return {
    id: 5,
    dataset_id: 7,
    dataset: DATASET,
    name: "159825 — A Grid 0.01 — 2026-07-20",
    status: "COMPLETED",
    configuration: CONFIGURATION,
    ohlc_path_mode: "AUTO",
    start_date: "2024-07-23",
    end_date: "2026-04-17",
    result_metrics: METRICS,
    error_message: null,
    created_at: "2026-07-20T10:00:00Z",
    completed_at: "2026-07-20T10:00:03Z",
    trades: [
      {
        id: 1,
        date: "2024-07-23",
        event_sequence: 1,
        side: "SELL",
        grid_price: "0.65900000",
        execution_price: "0.65800000",
        shares: 100,
        notional: "65.80000000",
        commission: "5.00000000",
        slippage_cost: "0.10000000",
        cash_after: "99725.20000000",
        shares_after: 9500,
        equity_after: "106584.90000000",
        status: "EXECUTED",
        skip_reason: null,
      },
      {
        id: 2,
        date: "2024-07-24",
        event_sequence: 2,
        side: "BUY",
        grid_price: "0.64900000",
        execution_price: null,
        shares: 100,
        notional: null,
        commission: null,
        slippage_cost: null,
        cash_after: "99725.20000000",
        shares_after: 9500,
        equity_after: "106584.90000000",
        status: "SKIPPED",
        skip_reason: "INSUFFICIENT_CASH",
      },
    ],
    zone_events: [
      { id: 1, date: "2024-08-01", event_sequence: 3, event_type: "ENTER_C_ZONE", price: "0.75900000" },
    ],
    daily_equity: [
      {
        id: 1,
        date: "2024-07-23",
        close: "0.63900000",
        cash: "100000",
        shares: 10000,
        equity: "106390.00000000",
        drawdown: "0.00000000",
        zone_at_close: "IN_A",
      },
      {
        id: 2,
        date: "2024-07-24",
        close: "0.64100000",
        cash: "99725.20000000",
        shares: 9500,
        equity: "107771.70000000",
        drawdown: "-0.01255742",
        zone_at_close: "OUTSIDE_C",
      },
    ],
    event_equity: [
      {
        id: 1,
        date: "2024-07-23",
        event_sequence: 1,
        market_price: "0.65900000",
        cash: "99725.20000000",
        shares: 9500,
        equity: "106584.90000000",
      },
    ],
    ...overrides,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;
let queues: Map<string, (() => Response | Promise<Response>)[]>;

function queueResponse(path: string, factory: () => Response | Promise<Response>) {
  const existing = queues.get(path) ?? [];
  existing.push(factory);
  queues.set(path, existing);
}

beforeEach(() => {
  push.mockClear();
  replace.mockClear();
  queues = new Map();
  fetchMock = vi.fn((url: string) => {
    const path = String(url);
    for (const [key, queue] of queues) {
      if (path.startsWith(key) && queue.length > 0) {
        return Promise.resolve(queue.shift()!());
      }
    }
    if (path === "/api/auth/me") return Promise.resolve(jsonResponse(AUTH_OK));
    return Promise.resolve(jsonResponse({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});

function detailCalls() {
  return fetchMock.mock.calls.filter((call) => String(call[0]).startsWith("/api/backtests/5"));
}

async function renderDetail(overrides: Record<string, unknown> = {}) {
  queueResponse("/api/backtests/5", () => jsonResponse(detail(overrides)));
  render(
    <AuthProvider>
      <BacktestDetailPage backtestId={5} />
    </AuthProvider>,
  );
  await screen.findByRole("heading", { name: /A Grid 0.01/ });
}

async function openTab(name: string) {
  await userEvent.click(screen.getByRole("tab", { name }));
}

describe("detail loading", () => {
  it("requests every series include exactly once", async () => {
    await renderDetail();
    expect(detailCalls()).toHaveLength(1);
    const url = new URL(String(detailCalls()[0][0]), "http://localhost");
    expect(url.searchParams.get("include")).toBe(
      "trades,zone_events,daily_equity,event_equity",
    );
  });

  it("shows an ownership-safe error for a missing run", async () => {
    queueResponse("/api/backtests/5", () =>
      jsonResponse(
        { error: { code: "BACKTEST_NOT_FOUND", message: "Backtest not found." } },
        404,
      ),
    );
    render(
      <AuthProvider>
        <BacktestDetailPage backtestId={5} />
      </AuthProvider>,
    );

    expect(await screen.findByText("Backtest unavailable")).toBeInTheDocument();
    expect(screen.getByText("Backtest not found.")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/another user|belongs to/i);
  });

  it("offers a retry after a network failure", async () => {
    queueResponse("/api/backtests/5", () => {
      throw new TypeError("Failed to fetch");
    });
    render(
      <AuthProvider>
        <BacktestDetailPage backtestId={5} />
      </AuthProvider>,
    );
    await screen.findByText("Backtest unavailable");

    queueResponse("/api/backtests/5", () => jsonResponse(detail()));
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: /A Grid 0.01/ })).toBeInTheDocument();
  });
});

describe("metrics presentation", () => {
  it("shows stored headline values verbatim", async () => {
    await renderDetail();
    expect(screen.getAllByText("107771.70000000").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1191.70000000").length).toBeGreaterThan(0);
    expect(screen.getAllByText("133").length).toBeGreaterThan(0);
  });

  it("adds a percentage to a ratio without altering the stored string", async () => {
    await renderDetail();
    // The exact stored ratio is kept in full; the percentage hint is
    // truncated and marked approximate rather than rounded.
    expect(
      screen.getAllByText(/0\.011181272283730531056483393 \(≈1\.1181%\)/).length,
    ).toBeGreaterThan(0);
  });

  it("preserves a negative drawdown", async () => {
    await renderDetail();
    expect(screen.getAllByText(/-0\.012557424/).length).toBeGreaterThan(0);
  });

  it("shows both benchmark summaries from stored metrics", async () => {
    await renderDetail();
    await openTab("Benchmarks");
    expect(screen.getByText("108470.00000000")).toBeInTheDocument();
    expect(screen.getByText("136940.82868000")).toBeInTheDocument();
    expect(screen.getByText("Benchmark 2 day-one purchase")).toBeInTheDocument();
  });

  it("shows costs and zone counts", async () => {
    await renderDetail();
    await openTab("Costs & zones");
    expect(screen.getByText("665")).toBeInTheDocument();
    expect(screen.getByText("13.300")).toBeInTheDocument();
    expect(screen.getByText("Zone event: ENTER_C_ZONE")).toBeInTheDocument();
  });
});

describe("configuration presentation", () => {
  it("renders every configuration group with exact values", async () => {
    await renderDetail();
    await openTab("Configuration");

    expect(screen.getByText("Portfolio")).toBeInTheDocument();
    expect(screen.getByText("Grid geometry")).toBeInTheDocument();
    expect(screen.getByText("Buy commission")).toBeInTheDocument();
    expect(screen.getByText("Sell commission")).toBeInTheDocument();
    expect(screen.getByText("0.06 (fixed mode)")).toBeInTheDocument();
    expect(screen.getByText("First close in the dataset")).toBeInTheDocument();
  });

  it("shows shared slippage correctly", async () => {
    await renderDetail();
    await openTab("Configuration");
    expect(screen.getByText("Both sides (shared)")).toBeInTheDocument();
  });

  it("shows separate slippage correctly", async () => {
    await renderDetail({
      configuration: {
        ...CONFIGURATION,
        slippage: {
          shared: false,
          mode: null,
          value: null,
          buy: { mode: "PERCENT", value: "0.002" },
          sell: { mode: "FIXED", value: "0.003" },
        },
      },
    });
    await openTab("Configuration");
    expect(screen.getByText("Buy and sell separately")).toBeInTheDocument();
    expect(screen.getByText("0.002")).toBeInTheDocument();
    expect(screen.getByText("0.003")).toBeInTheDocument();
  });

  it("shows enabled and disabled commission components", async () => {
    await renderDetail();
    await openTab("Configuration");
    expect(screen.getAllByText("Enabled").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Disabled").length).toBeGreaterThan(0);
  });

  it("states that a close-only dataset has no path mode", async () => {
    await renderDetail({ dataset: { ...DATASET, data_mode: "CLOSE_ONLY" } });
    await openTab("Configuration");
    expect(
      screen.getByText("Not applicable (close-only dataset)"),
    ).toBeInTheDocument();
  });
});

/** Every chart the Charts tab is required to offer, by accessible name. */
const CHART_NAMES = [
  /Price with buy and sell trades/,
  /Price with baseline and grid geometry/,
  /Strategy equity curve/,
  /Strategy against both benchmarks/,
  /Normalized performance/,
  /Drawdown/,
  /Trade activity per day/,
];

function chart(name: RegExp) {
  return screen.getByRole("img", { name });
}

describe("charts", () => {
  it("renders every chart with an accessible name and description", async () => {
    await renderDetail();
    await openTab("Charts");
    for (const name of CHART_NAMES) {
      const figure = chart(name);
      expect(figure, String(name)).toBeInTheDocument();
      // role="img" alone is not enough: each must carry a <desc> too, so the
      // chart is explained rather than just named.
      expect(figure.querySelector("desc")?.textContent ?? "").not.toBe("");
    }
  });

  it("groups the charts under labelled sections", async () => {
    await renderDetail();
    await openTab("Charts");
    for (const heading of ["Price and trades", "Equity and performance", "Risk and activity"]) {
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    }
  });

  it("labels the benchmark series in every multi-series legend", async () => {
    await renderDetail();
    await openTab("Charts");
    // Present in both the absolute and the normalized comparison.
    expect(screen.getAllByText(/Benchmark 1 \(hold initial portfolio\)/)).toHaveLength(2);
    expect(screen.getAllByText(/Benchmark 2 \(invest cash on day one\)/)).toHaveLength(2);
    expect(screen.getAllByText("Strategy equity").length).toBeGreaterThan(0);
  });

  it("reports the deepest drawdown using the stored string", async () => {
    await renderDetail();
    await openTab("Charts");
    expect(screen.getByText(/-0\.01255742/)).toBeInTheDocument();
  });

  it("states how many persisted grid levels were drawn", async () => {
    await renderDetail();
    await openTab("Charts");
    expect(screen.getByText(/Showing the 2 grid level/)).toBeInTheDocument();
  });

  it("says so honestly when no grid levels were stored", async () => {
    await renderDetail({ result_metrics: { ...METRICS, grid_levels: [] } });
    await openTab("Charts");
    expect(screen.getByText(/stored no individual grid levels/)).toBeInTheDocument();
  });

  it("quotes stored equity figures rather than deriving them", async () => {
    await renderDetail();
    await openTab("Charts");
    expect(screen.getByText(/Stored initial equity/)).toBeInTheDocument();
    // The exact stored strings, not a rounded or recomputed pair.
    expect(screen.getAllByText("106580.00000000").length).toBeGreaterThan(0);
    expect(screen.getAllByText("107771.70000000").length).toBeGreaterThan(0);
  });

  it("renders a single-point series safely", async () => {
    await renderDetail({
      daily_equity: [
        {
          id: 1,
          date: "2024-07-23",
          close: "0.639",
          cash: "1",
          shares: 1,
          equity: "106390.0",
          drawdown: "0",
          zone_at_close: "IN_A",
        },
      ],
    });
    await openTab("Charts");
    expect(chart(/Strategy equity curve/)).toBeInTheDocument();
    expect(chart(/Price with buy and sell trades/)).toBeInTheDocument();
  });
});

function executedTrade(overrides: Record<string, unknown>) {
  return {
    id: 1,
    date: "2024-07-23",
    event_sequence: 1,
    side: "BUY",
    grid_price: "0.65900000",
    execution_price: "0.65800000",
    shares: 100,
    notional: "65.80000000",
    commission: "5.00000000",
    slippage_cost: "0.10000000",
    cash_after: "99725.20000000",
    shares_after: 9500,
    equity_after: "106584.90000000",
    status: "EXECUTED",
    skip_reason: null,
    ...overrides,
  };
}

describe("trade markers", () => {
  it("marks executed buys and sells distinctly in the legend", async () => {
    await renderDetail({
      trades: [
        executedTrade({ id: 1, side: "BUY", date: "2024-07-23" }),
        executedTrade({ id: 2, side: "SELL", date: "2024-07-24", event_sequence: 2 }),
      ],
    });
    await openTab("Charts");

    // Two legend keys, each drawn as the triangle the chart itself uses, so
    // the sides are told apart by shape and not by colour alone.
    expect(screen.getByText("Buy (executed)")).toBeInTheDocument();
    expect(screen.getByText("Sell (executed)")).toBeInTheDocument();
    expect(screen.getByText(/1 buy and 1 sell marker/)).toBeInTheDocument();
  });

  it("keys only the sides it actually drew", async () => {
    // The fixture's only executed trade is a sell; a buy glyph appears
    // nowhere, so keying one would describe notation the chart never used.
    await renderDetail();
    await openTab("Charts");
    expect(screen.getByText("Sell (executed)")).toBeInTheDocument();
    expect(screen.queryByText("Buy (executed)")).not.toBeInTheDocument();
  });

  it("plots one marker per executed trade and no marker for a skipped one", async () => {
    await renderDetail();
    await openTab("Charts");
    // The fixture holds one executed SELL and one SKIPPED BUY.
    expect(screen.getByText(/0 buy and 1 sell marker/)).toBeInTheDocument();
    expect(
      screen.getByText(/1 trade\(s\) are not drawn because they were skipped/),
    ).toBeInTheDocument();
  });

  it("collapses same-day, same-price trades into one counted marker", async () => {
    const repeated = Array.from({ length: 3 }, (_, index) => ({
      id: index + 1,
      date: "2024-07-23",
      event_sequence: index + 1,
      side: "BUY",
      grid_price: "0.65900000",
      execution_price: "0.65800000",
      shares: 100,
      notional: "65.80000000",
      commission: "5.00000000",
      slippage_cost: "0.10000000",
      cash_after: "99725.20000000",
      shares_after: 9500,
      equity_after: "106584.90000000",
      status: "EXECUTED",
      skip_reason: null,
    }));
    await renderDetail({ trades: repeated });
    await openTab("Charts");
    expect(screen.getByText(/1 buy and 0 sell marker/)).toBeInTheDocument();
    expect(screen.getByText(/sharing a date and price share one marker/)).toBeInTheDocument();
  });

  it("does not plot a trade whose date is outside the daily series", async () => {
    await renderDetail({
      trades: [
        {
          id: 1,
          date: "2030-01-01",
          event_sequence: 1,
          side: "BUY",
          grid_price: "0.65900000",
          execution_price: "0.65800000",
          shares: 100,
          notional: "65.80000000",
          commission: "5.00000000",
          slippage_cost: "0.10000000",
          cash_after: "99725.20000000",
          shares_after: 9500,
          equity_after: "106584.90000000",
          status: "EXECUTED",
          skip_reason: null,
        },
      ],
    });
    await openTab("Charts");
    expect(screen.getByText(/No executed trade could be placed/)).toBeInTheDocument();
    expect(screen.getByText(/fell outside the daily series/)).toBeInTheDocument();
  });

  it("counts executed trades per day and quotes the stored totals", async () => {
    await renderDetail();
    await openTab("Charts");
    expect(screen.getByText("Executed buys")).toBeInTheDocument();
    expect(screen.getByText("Executed sells")).toBeInTheDocument();
    // 64 and 69 come from the stored trade_costs block, not from the two
    // fixture rows, so the caption cannot drift from the metric tables.
    expect(screen.getByText(/The stored result records/)).toBeInTheDocument();
    expect(screen.getByText("64")).toBeInTheDocument();
    expect(screen.getByText("69")).toBeInTheDocument();
  });
});

describe("normalized performance", () => {
  it("says plainly that the comparison chart is normalized", async () => {
    await renderDetail();
    await openTab("Charts");
    expect(
      chart(/Normalized performance \(each series rebased to 100\)/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Normalized for visual comparison only/)).toBeInTheDocument();
  });

  it("omits a series that started at zero instead of drawing a flat line", async () => {
    await renderDetail({
      result_metrics: {
        ...METRICS,
        benchmark1: {
          points: [
            { date: "2024-07-23", close: "0.639", cash: "0", shares: 0, equity: "0" },
            { date: "2024-07-24", close: "0.641", cash: "0", shares: 0, equity: "0" },
          ],
          day_one_purchase: null,
        },
      },
    });
    await openTab("Charts");
    expect(screen.getByText(/started at zero, so no ratio is defined/)).toBeInTheDocument();
  });

  it("names a benchmark that stored no points rather than estimating it", async () => {
    await renderDetail({
      result_metrics: { ...METRICS, benchmark2: { points: [], day_one_purchase: null } },
    });
    await openTab("Charts");
    expect(screen.getByText(/Benchmark 2 stored no equity points/)).toBeInTheDocument();
  });
});

describe("empty and failed chart states", () => {
  it("shows an empty state for every chart when no series was stored", async () => {
    await renderDetail({ daily_equity: [], trades: [], result_metrics: null });
    await openTab("Charts");

    // No chart may render a plot area without data behind it.
    expect(screen.queryAllByRole("img")).toHaveLength(0);
    expect(screen.getByText(/no stored daily equity series/i)).toBeInTheDocument();
    expect(screen.getByText(/no stored daily equity or benchmark series/i)).toBeInTheDocument();
    expect(screen.getByText(/no stored drawdown series/i)).toBeInTheDocument();
    expect(screen.getByText(/no stored series to normalize/i)).toBeInTheDocument();
    expect(
      screen.getByText(/no stored daily price series to plot trades against/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/no executed trades on the daily axis/i)).toBeInTheDocument();
  });

  it("shows clean chart empty states for a FAILED run", async () => {
    await renderDetail({
      status: "FAILED",
      result_metrics: null,
      error_message: "Non-positive execution price.",
      trades: [],
      zone_events: [],
      daily_equity: [],
      event_equity: [],
    });
    await openTab("Charts");

    expect(screen.queryAllByRole("img")).toHaveLength(0);
    // The failure is still reported, and no chart invents a figure.
    expect(screen.getByText("This run did not complete")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("107771.70000000");
  });

  it("plots the price line when a run stored days but no trades", async () => {
    await renderDetail({ trades: [] });
    await openTab("Charts");
    expect(chart(/Price with buy and sell trades/)).toBeInTheDocument();
    expect(screen.getByText(/No executed trade could be placed/)).toBeInTheDocument();
    // A day series with no trades is an activity chart with nothing to stack.
    expect(screen.getByText(/no executed trades on the daily axis/i)).toBeInTheDocument();
  });
});

describe("result tables", () => {
  it("renders every public trade field and no internal foreign key", async () => {
    await renderDetail();
    await openTab("Result tables");

    const trades = screen.getByRole("table", { name: /Every trade this run recorded/ });
    expect(within(trades).getByText("0.65900000")).toBeInTheDocument();
    expect(within(trades).getByText("EXECUTED")).toBeInTheDocument();
    expect(within(trades).getByText("SKIPPED")).toBeInTheDocument();
    expect(within(trades).getByText("Insufficient cash")).toBeInTheDocument();
    // The projection carries no event_id/backtest_run_id, and none is shown.
    expect(trades.textContent).not.toMatch(/event_id|backtest_run_id/);
  });

  it("shows a neutral dash for null trade values", async () => {
    await renderDetail();
    await openTab("Result tables");
    const trades = screen.getByRole("table", { name: /Every trade/ });
    expect(within(trades).getAllByText("—").length).toBeGreaterThanOrEqual(3);
    expect(trades.textContent).not.toContain("null");
  });

  it("renders all four series with their totals", async () => {
    await renderDetail();
    await openTab("Result tables");
    // Trades and daily equity both have two rows here.
    expect(screen.getAllByText("Showing 2 of 2 rows").length).toBe(2);
    expect(screen.getAllByText("Showing 1 of 1 row").length).toBe(2);
    expect(screen.getByRole("table", { name: /Zone boundary transitions/ })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /One row per trading day/ })).toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: /Portfolio equity captured at each event/ }),
    ).toBeInTheDocument();
  });

  it("shows empty states for absent series", async () => {
    await renderDetail({ trades: [], zone_events: [], daily_equity: [], event_equity: [] });
    await openTab("Result tables");
    expect(screen.getByText("No trades")).toBeInTheDocument();
    expect(screen.getByText("No zone events")).toBeInTheDocument();
    expect(screen.getByText("No daily equity")).toBeInTheDocument();
    expect(screen.getByText("No event equity")).toBeInTheDocument();
  });

  it("reveals more rows without dropping any", async () => {
    const many = Array.from({ length: 60 }, (_, index) => ({
      id: index + 1,
      date: "2024-07-23",
      event_sequence: index + 1,
      event_type: "ENTER_C_ZONE",
      price: "0.75900000",
    }));
    await renderDetail({ zone_events: many });
    await openTab("Result tables");

    expect(screen.getByText("Showing 50 of 60 rows")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show 10 more" }));
    expect(screen.getByText("Showing 60 of 60 rows")).toBeInTheDocument();
  });
});

describe("failed and pending runs", () => {
  it("shows a FAILED run's error and no fabricated metrics", async () => {
    await renderDetail({
      status: "FAILED",
      result_metrics: null,
      error_message: "Non-positive execution price.",
      trades: [],
      zone_events: [],
      daily_equity: [],
      event_equity: [],
    });

    expect(screen.getByText("This run did not complete")).toBeInTheDocument();
    expect(screen.getByText("Non-positive execution price.")).toBeInTheDocument();
    expect(
      screen.getByText(/no result metrics are stored for this run/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("107771.70000000")).not.toBeInTheDocument();
  });

  it("shows a PENDING run without inventing progress", async () => {
    await renderDetail({
      status: "PENDING",
      result_metrics: null,
      completed_at: null,
      trades: [],
      zone_events: [],
      daily_equity: [],
      event_equity: [],
    });

    expect(screen.getByText(/this run is pending/i)).toBeInTheDocument();
    expect(screen.getByText(/result data is not available yet/i)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\d+%/);
  });
});

describe("export controls", () => {
  it("offers the four downloads as links, never as buttons", async () => {
    await renderDetail();

    // Native navigations: the browser streams the file, so no button — and no
    // JavaScript — is involved. Full coverage lives in export-controls.test.tsx.
    expect(screen.getAllByRole("link", { name: /^Download/ })).toHaveLength(4);
    expect(
      screen.queryByRole("button", { name: /download|csv|pdf|export/i }),
    ).not.toBeInTheDocument();
  });
});
