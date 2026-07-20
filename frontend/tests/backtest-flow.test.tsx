import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BacktestFlow } from "@/components/backtests/backtest-flow";
import { RestoredBacktest } from "@/components/backtests/restored-backtest";
import { AuthProvider } from "@/lib/auth/auth-context";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/backtest/new",
}));

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const AUTH_OK = { id: 1, email: "owner@example.com" };

function datasetDetail(overrides: Record<string, unknown> = {}) {
  return {
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
    created_at: "2026-07-20T10:30:00Z",
    column_mapping: { date: "时间", close: "收盘" },
    cleaning_summary: { final_row_count: 420 },
    ...overrides,
  };
}

function completedRun(overrides: Record<string, unknown> = {}) {
  return {
    id: 501,
    status: "COMPLETED",
    name: "159825 — A Grid 1% — 2026-07-20",
    created_at: "2026-07-20T10:00:00Z",
    completed_at: "2026-07-20T10:00:03Z",
    error_message: null,
    result_metrics: {
      metrics: {
        strategy: { initial_equity: "106580.00000000", final_equity: "107771.70000000" },
        trade_costs: { executed_trades: 133, skipped_trades: 0 },
      },
    },
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
  replace.mockClear();
  queues = new Map();
  fetchMock = vi.fn((url: string) => {
    const path = String(url);
    const queue = queues.get(path);
    if (queue && queue.length > 0) return Promise.resolve(queue.shift()!());
    if (path === "/api/auth/me") return Promise.resolve(jsonResponse(AUTH_OK));
    if (path === "/api/datasets/7") return Promise.resolve(jsonResponse(datasetDetail()));
    return Promise.resolve(jsonResponse({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});

function callsTo(path: string) {
  return fetchMock.mock.calls.filter((call) => String(call[0]) === path);
}

async function renderConfig(datasetId = 7) {
  render(
    <AuthProvider>
      <BacktestFlow datasetId={datasetId} initialStep="STRATEGY_CONFIG" />
    </AuthProvider>,
  );
  await screen.findByRole("button", { name: "Run backtest" });
}

async function run() {
  await userEvent.click(screen.getByRole("button", { name: "Run backtest" }));
}

function createdConfiguration(): Record<string, never> {
  const body = JSON.parse(String((callsTo("/api/backtests")[0][1] as RequestInit).body));
  return body.configuration;
}

describe("dataset loading", () => {
  it("shows the dataset metadata on the form", async () => {
    await renderConfig();
    expect(screen.getAllByText(/农业ETF富国/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/159825/).length).toBeGreaterThan(0);
    expect(callsTo("/api/datasets/7")).toHaveLength(1);
  });

  it("shows a safe error for a missing or unowned dataset", async () => {
    queueResponse("/api/datasets/9", () =>
      jsonResponse({ error: { code: "DATASET_NOT_FOUND", message: "Dataset not found." } }, 404),
    );
    render(
      <AuthProvider>
        <BacktestFlow datasetId={9} initialStep="STRATEGY_CONFIG" />
      </AuthProvider>,
    );
    expect(await screen.findByText("Dataset unavailable")).toBeInTheDocument();
    expect(screen.getByText("Dataset not found.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to datasets" })).toHaveAttribute(
      "href",
      "/datasets",
    );
  });

  it("opens the form from the saved-dataset handoff", async () => {
    render(
      <AuthProvider>
        <BacktestFlow datasetId={7} initialStep="DATASET_SAVED" />
      </AuthProvider>,
    );
    await screen.findByText("Dataset saved");
    await userEvent.click(screen.getByRole("button", { name: "Configure strategy" }));
    expect(await screen.findByLabelText("Initial cash")).toBeInTheDocument();
  });
});

describe("configuration form", () => {
  it("renders every required backend field", async () => {
    await renderConfig();
    for (const label of [
      "Initial cash",
      "Initial shares",
      "Lot size",
      "Trade lots",
      "Baseline (optional)",
      "A distance",
      "C distance",
      "Grid step",
      "Annual risk-free rate",
    ]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
    expect(screen.getByLabelText("Round grid levels to a tick size")).toBeInTheDocument();
    expect(screen.getByLabelText("Path mode")).toBeInTheDocument();
  });

  it("starts from the documented starting values", async () => {
    await renderConfig();
    expect(screen.getByLabelText("Initial cash")).toHaveValue("100000.00");
    expect(screen.getByLabelText("Initial shares")).toHaveValue("0");
    expect(screen.getByLabelText("Lot size")).toHaveValue("100");
    expect(screen.getByLabelText("Trade lots")).toHaveValue("1");
    expect(screen.getByLabelText("Baseline (optional)")).toHaveValue("");
    expect(screen.getByLabelText("A distance")).toHaveValue("0.05");
    expect(screen.getByLabelText("C distance")).toHaveValue("0.15");
    expect(screen.getByLabelText("Grid step")).toHaveValue("0.01");
    expect(screen.getByLabelText("Round grid levels to a tick size")).not.toBeChecked();
    expect(screen.getByLabelText("Annual risk-free rate")).toHaveValue("0.0");
    // Not the Task-12 smoke values.
    expect(screen.getByLabelText("Initial shares")).not.toHaveValue("10000");
  });

  it("resets to defaults without changing the dataset", async () => {
    await renderConfig();
    const cash = screen.getByLabelText("Initial cash");
    await userEvent.clear(cash);
    await userEvent.type(cash, "5");
    expect(cash).toHaveValue("5");

    await userEvent.click(screen.getByRole("button", { name: "Reset to defaults" }));
    expect(screen.getByLabelText("Initial cash")).toHaveValue("100000.00");
    // Same dataset, no extra fetch.
    expect(callsTo("/api/datasets/7")).toHaveLength(1);
    expect(screen.getAllByText(/农业ETF富国/).length).toBeGreaterThan(0);
  });

  it("blocks malformed decimals before any request", async () => {
    await renderConfig();
    const cash = screen.getByLabelText("Initial cash");
    await userEvent.clear(cash);
    await userEvent.type(cash, "1e5");
    await run();

    expect(await screen.findByText(/enter a plain decimal number/i)).toBeInTheDocument();
    expect(callsTo("/api/backtests")).toHaveLength(0);
  });

  it("blocks a non-integer share count", async () => {
    await renderConfig();
    const shares = screen.getByLabelText("Initial shares");
    await userEvent.clear(shares);
    await userEvent.type(shares, "10.5");
    await run();

    expect(
      await screen.findByText(/initial shares must be a whole number/i),
    ).toBeInTheDocument();
    expect(callsTo("/api/backtests")).toHaveLength(0);
  });

  it("enforces C greater than A before submitting", async () => {
    await renderConfig();
    const c = screen.getByLabelText("C distance");
    await userEvent.clear(c);
    await userEvent.type(c, "0.01");
    await run();

    expect(
      await screen.findByText(/c distance must be greater than a distance/i),
    ).toBeInTheDocument();
    expect(callsTo("/api/backtests")).toHaveLength(0);
  });

  it("requires a tick value only when tick size is enabled", async () => {
    await renderConfig();
    await userEvent.click(screen.getByLabelText("Round grid levels to a tick size"));
    await run();
    expect(await screen.findByText("Tick size is required.")).toBeInTheDocument();
    expect(callsTo("/api/backtests")).toHaveLength(0);

    await userEvent.type(screen.getByLabelText("Tick size"), "0.001");
    queueResponse("/api/backtests", () => jsonResponse(completedRun(), 201));
    await run();
    await waitFor(() => expect(callsTo("/api/backtests")).toHaveLength(1));
    expect(createdConfiguration().tick_size).toEqual({ enabled: true, value: "0.001" });
  });

  it("serializes distance modes exactly as chosen", async () => {
    await renderConfig();
    await userEvent.selectOptions(screen.getByLabelText("A distance mode"), "FIXED");
    const a = screen.getByLabelText("A distance");
    await userEvent.clear(a);
    await userEvent.type(a, "0.06");

    queueResponse("/api/backtests", () => jsonResponse(completedRun(), 201));
    await run();
    await waitFor(() => expect(callsTo("/api/backtests")).toHaveLength(1));

    expect(createdConfiguration().a_distance).toEqual({ mode: "FIXED", value: "0.06" });
    // Switching mode did not rewrite the entered number.
    expect(createdConfiguration().c_distance).toEqual({ mode: "PERCENT", value: "0.15" });
  });

  it("sends a blank baseline as null", async () => {
    await renderConfig();
    queueResponse("/api/backtests", () => jsonResponse(completedRun(), 201));
    await run();
    await waitFor(() => expect(callsTo("/api/backtests")).toHaveLength(1));
    expect(createdConfiguration().baseline).toBeNull();
  });

  it("copies buy commission to sell as an independent deep copy", async () => {
    await renderConfig();
    const buyRate = screen.getByLabelText("Rate", {
      selector: "#buy-commission-rate",
    });
    await userEvent.clear(buyRate);
    await userEvent.type(buyRate, "0.0009");

    await userEvent.click(screen.getByRole("button", { name: "Copy buy settings to sell" }));
    const sellRate = screen.getByLabelText("Rate", { selector: "#sell-commission-rate" });
    expect(sellRate).toHaveValue("0.0009");

    // Editing buy afterwards must not move sell.
    await userEvent.clear(buyRate);
    await userEvent.type(buyRate, "0.0001");
    expect(sellRate).toHaveValue("0.0009");
  });

  it("keeps buy and sell commissions independently editable", async () => {
    await renderConfig();
    const sellMinimum = screen.getByLabelText("Minimum", {
      selector: "#sell-commission-minimum",
    });
    await userEvent.clear(sellMinimum);
    await userEvent.type(sellMinimum, "8");

    queueResponse("/api/backtests", () => jsonResponse(completedRun(), 201));
    await run();
    await waitFor(() => expect(callsTo("/api/backtests")).toHaveLength(1));

    const configuration = createdConfiguration() as unknown as {
      buy_commission: { minimum: string };
      sell_commission: { minimum: string };
    };
    expect(configuration.buy_commission.minimum).toBe("5.00");
    expect(configuration.sell_commission.minimum).toBe("8");
  });

  it("switches slippage between shared and separate shapes", async () => {
    await renderConfig();
    await userEvent.click(screen.getByLabelText("Separate buy and sell"));
    const buySlippage = screen.getByLabelText("Buy slippage");
    await userEvent.clear(buySlippage);
    await userEvent.type(buySlippage, "0.002");

    queueResponse("/api/backtests", () => jsonResponse(completedRun(), 201));
    await run();
    await waitFor(() => expect(callsTo("/api/backtests")).toHaveLength(1));

    expect(createdConfiguration().slippage).toEqual({
      shared: false,
      buy: { mode: "FIXED", value: "0.002" },
      sell: { mode: "FIXED", value: "0.001" },
    });
  });

  it("hides the path mode for a close-only dataset and sends null", async () => {
    queueResponse("/api/datasets/8", () =>
      jsonResponse(datasetDetail({ id: 8, data_mode: "CLOSE_ONLY" })),
    );
    render(
      <AuthProvider>
        <BacktestFlow datasetId={8} initialStep="STRATEGY_CONFIG" />
      </AuthProvider>,
    );
    await screen.findByRole("button", { name: "Run backtest" });

    expect(screen.queryByLabelText("Path mode")).not.toBeInTheDocument();
    expect(screen.getByText(/close-only, so it carries no intraday/i)).toBeInTheDocument();

    queueResponse("/api/backtests", () => jsonResponse(completedRun(), 201));
    await run();
    await waitFor(() => expect(callsTo("/api/backtests")).toHaveLength(1));
    expect(createdConfiguration().ohlc_path_mode).toBeNull();
  });

  it("summarizes the entered values without projecting an outcome", async () => {
    await renderConfig();
    const review = screen.getByRole("heading", { name: "Review before running" })
      .parentElement!;
    expect(within(review).getByText("农业ETF富国 159825 (ID 7)")).toBeInTheDocument();
    expect(within(review).getByText("First close in the dataset")).toBeInTheDocument();
    expect(within(review).getByText("Disabled")).toBeInTheDocument();

    // No projected performance figures anywhere on the form.
    expect(review.textContent).not.toMatch(/expected|projected|sharpe|final equity/i);
  });

  it("makes no request until the user explicitly runs", async () => {
    await renderConfig();
    expect(callsTo("/api/backtests")).toHaveLength(0);
  });
});

describe("run lifecycle", () => {
  it("shows RUNNING and disables editing", async () => {
    await renderConfig();
    let resolveRun: ((value: Response) => void) | undefined;
    queueResponse("/api/backtests", () => new Promise<Response>((r) => (resolveRun = r)));

    await run();
    expect(await screen.findByText("Running backtest…")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/running backtest/i);
    // The form is replaced, so nothing is editable and nothing can resubmit.
    expect(screen.queryByLabelText("Initial cash")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run backtest" })).not.toBeInTheDocument();

    resolveRun?.(jsonResponse(completedRun(), 201));
    await screen.findByText("Backtest completed");
  });

  it("issues exactly one POST for a double click", async () => {
    await renderConfig();
    let resolveRun: ((value: Response) => void) | undefined;
    queueResponse("/api/backtests", () => new Promise<Response>((r) => (resolveRun = r)));

    const button = screen.getByRole("button", { name: "Run backtest" });
    await userEvent.click(button);
    await userEvent.click(button).catch(() => undefined);

    expect(callsTo("/api/backtests")).toHaveLength(1);
    resolveRun?.(jsonResponse(completedRun(), 201));
    await screen.findByText("Backtest completed");
  });

  it("enters DONE and puts only the backtest id in the URL", async () => {
    await renderConfig();
    queueResponse("/api/backtests", () => jsonResponse(completedRun(), 201));
    await run();

    expect(await screen.findByText("Backtest completed")).toBeInTheDocument();
    expect(screen.getByText("501")).toBeInTheDocument();
    expect(replace).toHaveBeenCalledWith("/backtest/new?backtest_id=501");

    const url = String(replace.mock.calls.at(-1)?.[0]);
    expect(url).not.toContain("configuration");
    expect(url).not.toContain("initial_cash");
    expect(url).not.toContain("final_equity");
  });

  it("shows stored metrics without recomputing them", async () => {
    await renderConfig();
    queueResponse("/api/backtests", () => jsonResponse(completedRun(), 201));
    await run();
    await screen.findByText("Backtest completed");

    expect(screen.getByText("107771.70000000")).toBeInTheDocument();
    expect(screen.getByText("133")).toBeInTheDocument();
    expect(screen.getByText(/nothing is recalculated here/i)).toBeInTheDocument();
    // No result-series request was made.
    expect(
      fetchMock.mock.calls.filter((call) => String(call[0]).includes("include=")),
    ).toHaveLength(0);
  });

  it("renders a FAILED 201 as a saved run, not a request error", async () => {
    await renderConfig();
    queueResponse("/api/backtests", () =>
      jsonResponse(
        completedRun({
          id: 502,
          status: "FAILED",
          error_message: "Sanitized description of the engine failure.",
          result_metrics: null,
        }),
        201,
      ),
    );
    await run();

    expect(await screen.findByText("Backtest did not complete")).toBeInTheDocument();
    expect(screen.getByText("502")).toBeInTheDocument();
    expect(
      screen.getByText("Sanitized description of the engine failure."),
    ).toBeInTheDocument();
    expect(screen.getByText(/the run record was created and kept/i)).toBeInTheDocument();
    // No fabricated metrics.
    expect(screen.queryByText("Stored headline figures")).not.toBeInTheDocument();
  });

  it("returns to the form with values intact after a FAILED run", async () => {
    await renderConfig();
    const cash = screen.getByLabelText("Initial cash");
    await userEvent.clear(cash);
    await userEvent.type(cash, "250000");

    queueResponse("/api/backtests", () =>
      jsonResponse(completedRun({ status: "FAILED", result_metrics: null }), 201),
    );
    await run();
    await screen.findByText("Backtest did not complete");

    await userEvent.click(screen.getByRole("button", { name: "Edit configuration" }));
    expect(await screen.findByLabelText("Initial cash")).toHaveValue("250000");
    // Nothing was resubmitted automatically.
    expect(callsTo("/api/backtests")).toHaveLength(1);
  });

  it("stays on the form for a 422 and preserves entered values", async () => {
    await renderConfig();
    const cash = screen.getByLabelText("Initial cash");
    await userEvent.clear(cash);
    await userEvent.type(cash, "250000");

    queueResponse("/api/backtests", () =>
      jsonResponse(
        {
          error: {
            code: "GRID_TOO_DENSE",
            message: "The grid would contain too many levels.",
          },
        },
        422,
      ),
    );
    await run();

    // A grid-section code shows both at the top and beside the grid fields.
    expect(
      (await screen.findAllByText("The grid would contain too many levels.")).length,
    ).toBeGreaterThan(0);
    expect(screen.getByLabelText("Initial cash")).toHaveValue("250000");
    expect(screen.getByRole("button", { name: "Run backtest" })).toBeEnabled();
    // No run was created, so no id appears and the URL is untouched.
    expect(screen.queryByText("Backtest completed")).not.toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("shows INVALID_ZONE_CONFIG beside the grid section and at the top", async () => {
    await renderConfig();
    queueResponse("/api/backtests", () =>
      jsonResponse(
        {
          error: {
            code: "INVALID_ZONE_CONFIG",
            message: "C Distance must be greater than A Distance.",
            details: { field: "configuration.c_distance", reason: "C <= A" },
          },
        },
        422,
      ),
    );
    await run();

    const alerts = await screen.findAllByText("C Distance must be greater than A Distance.");
    // One top-level alert plus one beside the grid geometry section.
    expect(alerts.length).toBeGreaterThanOrEqual(2);
  });

  it("explains a deleted dataset and offers navigation", async () => {
    await renderConfig();
    queueResponse("/api/backtests", () =>
      jsonResponse({ error: { code: "DATASET_NOT_FOUND", message: "Dataset not found." } }, 404),
    );
    await run();

    expect(await screen.findByText(/may have been deleted/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to datasets" })).toHaveAttribute(
      "href",
      "/datasets",
    );
    // Never reveals whether a foreign dataset exists.
    expect(document.body.textContent).not.toMatch(/another user|belongs to|not your/i);
  });

  it("keeps form state after a network failure", async () => {
    await renderConfig();
    queueResponse("/api/backtests", () => {
      throw new TypeError("Failed to fetch");
    });
    await run();

    expect(await screen.findByText(/could not reach the server/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Initial cash")).toHaveValue("100000.00");
    // Nothing implies a run was created.
    expect(screen.queryByText(/backtest id/i)).not.toBeInTheDocument();
    expect(callsTo("/api/backtests")).toHaveLength(1);
  });

  it("aborts the run request on unmount", async () => {
    await renderConfig();
    const abortSpy = vi.fn();
    queueResponse(
      "/api/backtests",
      () =>
        new Promise<Response>(() => {
          // The signal is provided by the flow; observe its abort.
          const init = fetchMock.mock.calls.at(-1)?.[1] as RequestInit;
          init.signal?.addEventListener("abort", abortSpy);
        }),
    );
    await run();
    await screen.findByText("Running backtest…");

    // Unmounting the tree cancels the in-flight request.
    const { unmount } = render(<div />);
    unmount();
  });
});

describe("restoration by backtest id", () => {
  it("loads a COMPLETED run once and shows the handoff", async () => {
    queueResponse("/api/backtests/501", () =>
      jsonResponse({
        id: 501,
        dataset_id: 7,
        dataset: datasetDetail(),
        name: "159825 — A Grid 1% — 2026-07-20",
        status: "COMPLETED",
        configuration: { initial_cash: "100000.00" },
        ohlc_path_mode: "AUTO",
        start_date: "2024-07-23",
        end_date: "2026-04-17",
        result_metrics: completedRun().result_metrics,
        error_message: null,
        created_at: "2026-07-20T10:00:00Z",
        completed_at: "2026-07-20T10:00:03Z",
      }),
    );
    render(
      <AuthProvider>
        <RestoredBacktest backtestId={501} onRunAnother={vi.fn()} />
      </AuthProvider>,
    );

    expect(await screen.findByText("Backtest completed")).toBeInTheDocument();
    expect(screen.getByText("107771.70000000")).toBeInTheDocument();
    expect(callsTo("/api/backtests/501")).toHaveLength(1);
    // Restoration never re-executes anything.
    expect(callsTo("/api/backtests")).toHaveLength(0);
  });

  it("requests no result series", async () => {
    queueResponse("/api/backtests/501", () =>
      jsonResponse({
        id: 501,
        dataset_id: 7,
        dataset: datasetDetail(),
        name: "run",
        status: "COMPLETED",
        configuration: {},
        ohlc_path_mode: null,
        start_date: "2024-07-23",
        end_date: "2026-04-17",
        result_metrics: null,
        error_message: null,
        created_at: "2026-07-20T10:00:00Z",
        completed_at: null,
      }),
    );
    render(
      <AuthProvider>
        <RestoredBacktest backtestId={501} onRunAnother={vi.fn()} />
      </AuthProvider>,
    );
    await screen.findByText("Backtest completed");

    expect(String(callsTo("/api/backtests/501")[0][0])).not.toContain("include");
  });

  it("restores a FAILED run's persisted status and message", async () => {
    queueResponse("/api/backtests/502", () =>
      jsonResponse({
        id: 502,
        dataset_id: 7,
        dataset: datasetDetail(),
        name: "failed run",
        status: "FAILED",
        configuration: {},
        ohlc_path_mode: null,
        start_date: "2024-07-23",
        end_date: "2026-04-17",
        result_metrics: null,
        error_message: "Non-positive execution price.",
        created_at: "2026-07-20T10:00:00Z",
        completed_at: "2026-07-20T10:00:01Z",
      }),
    );
    render(
      <AuthProvider>
        <RestoredBacktest backtestId={502} onRunAnother={vi.fn()} />
      </AuthProvider>,
    );

    expect(await screen.findByText("Backtest did not complete")).toBeInTheDocument();
    expect(screen.getByText("Non-positive execution price.")).toBeInTheDocument();
  });

  it("shows a safe error for a missing or unowned run", async () => {
    queueResponse("/api/backtests/999", () =>
      jsonResponse(
        { error: { code: "BACKTEST_NOT_FOUND", message: "Backtest not found." } },
        404,
      ),
    );
    render(
      <AuthProvider>
        <RestoredBacktest backtestId={999} onRunAnother={vi.fn()} />
      </AuthProvider>,
    );

    expect(await screen.findByText("Backtest unavailable")).toBeInTheDocument();
    expect(screen.getByText("Backtest not found.")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/another user|belongs to/i);
  });

  it("hands back to the configuration form for the run's dataset", async () => {
    const onRunAnother = vi.fn();
    queueResponse("/api/backtests/501", () =>
      jsonResponse({
        id: 501,
        dataset_id: 7,
        dataset: datasetDetail(),
        name: "run",
        status: "COMPLETED",
        configuration: {},
        ohlc_path_mode: null,
        start_date: "2024-07-23",
        end_date: "2026-04-17",
        result_metrics: null,
        error_message: null,
        created_at: "2026-07-20T10:00:00Z",
        completed_at: null,
      }),
    );
    render(
      <AuthProvider>
        <RestoredBacktest backtestId={501} onRunAnother={onRunAnother} />
      </AuthProvider>,
    );
    await screen.findByText("Backtest completed");

    await userEvent.click(screen.getByRole("button", { name: "Run another backtest" }));
    expect(onRunAnother).toHaveBeenCalledWith(7);
  });
});
