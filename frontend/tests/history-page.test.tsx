import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CompareResults } from "@/components/backtests/compare-results";
import { BacktestHistoryPage } from "@/components/history/backtest-history-page";
import { AuthProvider } from "@/lib/auth/auth-context";

const push = vi.fn();
let searchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => searchParams,
  usePathname: () => "/history",
}));

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const AUTH_OK = { id: 1, email: "owner@example.com" };

function listItem(overrides: Record<string, unknown> = {}) {
  return {
    id: 5,
    dataset_id: 7,
    dataset_name: "农业ETF富国 159825",
    name: "159825 — A Grid 0.01 — 2026-07-20",
    status: "COMPLETED",
    start_date: "2024-07-23",
    end_date: "2026-04-17",
    ohlc_path_mode: "AUTO",
    created_at: "2026-07-20T10:00:00Z",
    completed_at: "2026-07-20T10:00:03Z",
    error_message: null,
    result_metrics: {
      metrics: {
        strategy: { final_equity: "107771.70000000", net_profit: "1191.70000000" },
        trade_costs: { executed_trades: 133 },
      },
    },
    ...overrides,
  };
}

function listResponse(items: unknown[], total = items.length) {
  return { items, total, limit: 20, offset: 0 };
}

let fetchMock: ReturnType<typeof vi.fn>;
let queues: Map<string, (() => Response | Promise<Response>)[]>;

function queueResponse(prefix: string, factory: () => Response | Promise<Response>) {
  const existing = queues.get(prefix) ?? [];
  existing.push(factory);
  queues.set(prefix, existing);
}

beforeEach(() => {
  push.mockClear();
  searchParams = new URLSearchParams();
  queues = new Map();
  fetchMock = vi.fn((url: string) => {
    const path = String(url);
    for (const [prefix, queue] of queues) {
      if (path.startsWith(prefix) && queue.length > 0) {
        return Promise.resolve(queue.shift()!());
      }
    }
    if (path === "/api/auth/me") return Promise.resolve(jsonResponse(AUTH_OK));
    if (path.startsWith("/api/datasets")) {
      return Promise.resolve(jsonResponse({ items: [] }));
    }
    if (path.startsWith("/api/backtests")) {
      return Promise.resolve(jsonResponse(listResponse([])));
    }
    return Promise.resolve(jsonResponse({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});

function backtestListCalls() {
  return fetchMock.mock.calls.filter((call) =>
    /^\/api\/backtests(\?|$)/.test(String(call[0])),
  );
}

async function renderHistory(items: unknown[] = [listItem()], total?: number) {
  queueResponse("/api/backtests", () => jsonResponse(listResponse(items, total)));
  render(
    <AuthProvider>
      <BacktestHistoryPage />
    </AuthProvider>,
  );
  await waitFor(() => expect(backtestListCalls().length).toBeGreaterThan(0));
}

describe("history list", () => {
  it("renders each run's summary fields including Chinese metadata", async () => {
    await renderHistory();
    expect(await screen.findByText(/A Grid 0.01/)).toBeInTheDocument();
    expect(screen.getByText(/农业ETF富国 159825/)).toBeInTheDocument();
    expect(screen.getAllByText("Completed").length).toBeGreaterThan(0);
    expect(screen.getByText("2024-07-23 to 2026-04-17")).toBeInTheDocument();
    expect(screen.getByText("AUTO")).toBeInTheDocument();
    expect(screen.getByText("107771.70000000")).toBeInTheDocument();
  });

  it("shows the total count", async () => {
    await renderHistory([listItem()], 37);
    expect(await screen.findByText(/37 backtests found/)).toBeInTheDocument();
  });

  it("preserves the backend ordering", async () => {
    await renderHistory([
      listItem({ id: 9, name: "newest" }),
      listItem({ id: 3, name: "older" }),
    ]);
    await screen.findByText("newest");
    const headings = screen.getAllByRole("heading", { level: 3 });
    expect(headings[0]).toHaveTextContent("newest");
    expect(headings[1]).toHaveTextContent("older");
  });

  it("renders a FAILED run with its message and no metrics", async () => {
    await renderHistory([
      listItem({
        status: "FAILED",
        result_metrics: null,
        error_message: "Non-positive execution price.",
      }),
    ]);
    expect((await screen.findAllByText("Failed")).length).toBeGreaterThan(0);
    expect(screen.getByText("Non-positive execution price.")).toBeInTheDocument();
    expect(screen.queryByText("107771.70000000")).not.toBeInTheDocument();
    // Actions stay available on a failed run.
    expect(screen.getByRole("button", { name: /^Rerun / })).toBeInTheDocument();
  });

  it("shows an empty state when there are no runs at all", async () => {
    await renderHistory([]);
    expect(await screen.findByText("No backtests yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Run your first backtest" })).toHaveAttribute(
      "href",
      "/backtest/new",
    );
  });

  it("shows a filtered empty state when filters exclude everything", async () => {
    searchParams = new URLSearchParams("search=nothing");
    await renderHistory([]);
    expect(await screen.findByText("No backtests match these filters")).toBeInTheDocument();
  });

  it("offers a retry after a load failure", async () => {
    queueResponse("/api/backtests", () => {
      throw new TypeError("Failed to fetch");
    });
    render(
      <AuthProvider>
        <BacktestHistoryPage />
      </AuthProvider>,
    );
    expect(await screen.findByText("Could not load your backtests")).toBeInTheDocument();

    queueResponse("/api/backtests", () => jsonResponse(listResponse([listItem()])));
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(/A Grid 0.01/)).toBeInTheDocument();
  });

  it("links each row to its detail page", async () => {
    await renderHistory();
    await screen.findByText(/A Grid 0.01/);
    expect(
      screen.getByRole("link", { name: /View results for 159825/ }),
    ).toHaveAttribute("href", "/history/5");
  });

  it("makes one list request, not one per row", async () => {
    await renderHistory([listItem({ id: 1 }), listItem({ id: 2 }), listItem({ id: 3 })]);
    await screen.findAllByRole("heading", { level: 3 });
    expect(backtestListCalls()).toHaveLength(1);
    // No per-row detail request.
    const detailCalls = fetchMock.mock.calls.filter((call) =>
      /^\/api\/backtests\/\d+/.test(String(call[0])),
    );
    expect(detailCalls).toHaveLength(0);
  });

  it("offers no export controls yet", async () => {
    await renderHistory();
    await screen.findByText(/A Grid 0.01/);
    expect(
      screen.queryByRole("button", { name: /download|csv|pdf|export/i }),
    ).not.toBeInTheDocument();
  });
});

describe("filters and pagination", () => {
  it("sends the applied filters from the URL", async () => {
    searchParams = new URLSearchParams("search=grid&dataset_id=7&status=FAILED");
    await renderHistory([]);
    const url = new URL(String(backtestListCalls()[0][0]), "http://localhost");
    expect(url.searchParams.get("search")).toBe("grid");
    expect(url.searchParams.get("dataset_id")).toBe("7");
    expect(url.searchParams.get("status")).toBe("FAILED");
  });

  it("restores filter controls from the URL", async () => {
    searchParams = new URLSearchParams("search=grid&status=FAILED");
    await renderHistory([]);
    expect(await screen.findByLabelText("Search by name")).toHaveValue("grid");
    expect(screen.getByLabelText("Status")).toHaveValue("FAILED");
  });

  it("resets to page one when a filter changes", async () => {
    searchParams = new URLSearchParams("page=3");
    await renderHistory([listItem()]);
    await screen.findByText(/A Grid 0.01/);

    await userEvent.selectOptions(screen.getByLabelText("Status"), "COMPLETED");
    await waitFor(() => expect(push).toHaveBeenCalledWith("/history?status=COMPLETED"));
  });

  it("applies the offset for a later page", async () => {
    searchParams = new URLSearchParams("page=3");
    await renderHistory([]);
    const url = new URL(String(backtestListCalls()[0][0]), "http://localhost");
    expect(url.searchParams.get("offset")).toBe("40");
    expect(url.searchParams.get("limit")).toBe("20");
  });

  it("disables pagination at the boundaries", async () => {
    await renderHistory([listItem()], 45);
    await screen.findByText(/A Grid 0.01/);
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
  });

  it("navigates to the next page", async () => {
    await renderHistory([listItem()], 45);
    await screen.findByText(/A Grid 0.01/);
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(push).toHaveBeenCalledWith("/history?page=2");
  });
});

describe("comparison selection", () => {
  it("requires two selections before comparing", async () => {
    await renderHistory([listItem({ id: 5 }), listItem({ id: 6, name: "second" })]);
    await screen.findByText("second");

    await userEvent.click(screen.getByRole("checkbox", { name: /Select 159825.*comparison/ }));
    expect(screen.getByText(/select at least one more/i)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Compare selected" });
    expect(link).toHaveAttribute("aria-disabled", "true");
  });

  it("links to the compare page preserving selection order", async () => {
    await renderHistory([listItem({ id: 5 }), listItem({ id: 6, name: "second" })]);
    await screen.findByText("second");

    await userEvent.click(screen.getByRole("checkbox", { name: /Select second/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /Select 159825/ }));

    expect(screen.getByRole("link", { name: "Compare selected" })).toHaveAttribute(
      "href",
      "/history/compare?ids=6,5",
    );
  });

  it("clears the selection when filters change, with a notice", async () => {
    await renderHistory([listItem({ id: 5 }), listItem({ id: 6, name: "second" })]);
    await screen.findByText("second");
    await userEvent.click(screen.getByRole("checkbox", { name: /Select second/ }));
    expect(screen.getByText(/1 selected for comparison/)).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Status"), "COMPLETED");
    await waitFor(() =>
      expect(screen.queryByText(/selected for comparison/)).not.toBeInTheDocument(),
    );
  });

  it("can clear the selection explicitly", async () => {
    await renderHistory([listItem({ id: 5 })]);
    await screen.findByText(/A Grid 0.01/);
    await userEvent.click(screen.getByRole("checkbox", { name: /Select 159825/ }));
    await userEvent.click(screen.getByRole("button", { name: "Clear selection" }));
    expect(screen.queryByText(/selected for comparison/)).not.toBeInTheDocument();
  });
});

describe("history actions", () => {
  it("renames through one PATCH and updates the row", async () => {
    await renderHistory();
    await screen.findByText(/A Grid 0.01/);

    await userEvent.click(screen.getByRole("button", { name: /^Rename / }));
    const dialog = await screen.findByRole("dialog");
    const input = within(dialog).getByLabelText("Name");
    expect(input).toHaveValue("159825 — A Grid 0.01 — 2026-07-20");

    await userEvent.clear(input);
    await userEvent.type(input, "  Renamed run  ");
    queueResponse("/api/backtests/5", () => jsonResponse({ id: 5, name: "Renamed run" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Save name" }));

    await waitFor(() => expect(screen.getByText("Renamed run")).toBeInTheDocument());
    const patch = fetchMock.mock.calls.find(
      (call) => (call[1] as RequestInit).method === "PATCH",
    );
    // Trimmed, and only the name is ever sent.
    expect(JSON.parse(String((patch![1] as RequestInit).body))).toEqual({
      name: "Renamed run",
    });
  });

  it("blocks an empty rename without calling the API", async () => {
    await renderHistory();
    await screen.findByText(/A Grid 0.01/);
    await userEvent.click(screen.getByRole("button", { name: /^Rename / }));
    const dialog = await screen.findByRole("dialog");

    await userEvent.clear(within(dialog).getByLabelText("Name"));
    await userEvent.click(within(dialog).getByRole("button", { name: "Save name" }));

    expect(await screen.findByText("Enter a name for this backtest.")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter((call) => (call[1] as RequestInit).method === "PATCH"),
    ).toHaveLength(0);
  });

  it("cancelling rename performs no request", async () => {
    await renderHistory();
    await screen.findByText(/A Grid 0.01/);
    await userEvent.click(screen.getByRole("button", { name: /^Rename / }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(
      fetchMock.mock.calls.filter((call) => (call[1] as RequestInit).method === "PATCH"),
    ).toHaveLength(0);
  });

  it("deletes only after a 204 and removes just that row", async () => {
    await renderHistory([listItem({ id: 5 }), listItem({ id: 6, name: "second" })]);
    await screen.findByText("second");

    await userEvent.click(screen.getByRole("button", { name: /^Delete 159825/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/dataset and its price data are not affected/i)).toBeInTheDocument();

    queueResponse("/api/backtests/5", () => new Response(null, { status: 204 }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete backtest" }));

    await waitFor(() =>
      expect(
        screen.queryByRole("heading", { level: 3, name: /A Grid 0.01/ }),
      ).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("heading", { level: 3, name: "second" })).toBeInTheDocument();
  });

  it("keeps the row when deletion fails", async () => {
    await renderHistory();
    await screen.findByText(/A Grid 0.01/);
    await userEvent.click(screen.getByRole("button", { name: /^Delete / }));
    const dialog = await screen.findByRole("dialog");

    queueResponse("/api/backtests/5", () => {
      throw new TypeError("Failed to fetch");
    });
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete backtest" }));

    await waitFor(() =>
      expect(within(screen.getByRole("dialog")).getByText(/could not reach the server/i)).toBeInTheDocument(),
    );
    expect(screen.getAllByText(/A Grid 0.01/).length).toBeGreaterThan(0);
  });

  it("reruns with one POST and opens the new run", async () => {
    await renderHistory();
    await screen.findByText(/A Grid 0.01/);
    await userEvent.click(screen.getByRole("button", { name: /^Rerun / }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/a new backtest is created/i)).toBeInTheDocument();

    queueResponse("/api/backtests/5/rerun", () =>
      jsonResponse({ id: 9, status: "COMPLETED", name: "rerun" }, 201),
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Rerun" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/history/9"));
    const reruns = fetchMock.mock.calls.filter((call) =>
      String(call[0]).endsWith("/rerun"),
    );
    expect(reruns).toHaveLength(1);
    expect((reruns[0][1] as RequestInit).body).toBeUndefined();
  });

  it("opens a FAILED rerun's saved run too", async () => {
    await renderHistory();
    await screen.findByText(/A Grid 0.01/);
    await userEvent.click(screen.getByRole("button", { name: /^Rerun / }));
    const dialog = await screen.findByRole("dialog");

    queueResponse("/api/backtests/5/rerun", () =>
      jsonResponse({ id: 10, status: "FAILED", name: "rerun" }, 201),
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Rerun" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/history/10"));
  });

  it("keeps the list intact when a rerun is rejected", async () => {
    await renderHistory();
    await screen.findByText(/A Grid 0.01/);
    await userEvent.click(screen.getByRole("button", { name: /^Rerun / }));
    const dialog = await screen.findByRole("dialog");

    queueResponse("/api/backtests/5/rerun", () =>
      jsonResponse(
        { error: { code: "VALIDATION_ERROR", message: "Dataset contains no price bars." } },
        422,
      ),
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Rerun" }));

    await waitFor(() =>
      expect(screen.getAllByText("Dataset contains no price bars.").length).toBeGreaterThan(0),
    );
    expect(push).not.toHaveBeenCalled();
    expect(screen.getAllByText(/A Grid 0.01/).length).toBeGreaterThan(0);
  });

  it("duplicates with the full edited configuration", async () => {
    await renderHistory();
    await screen.findByText(/A Grid 0.01/);

    queueResponse("/api/backtests/5", () =>
      jsonResponse({
        id: 5,
        dataset_id: 7,
        dataset: {
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
        },
        name: "source",
        status: "COMPLETED",
        configuration: {
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
        },
        ohlc_path_mode: "AUTO",
        start_date: "2024-07-23",
        end_date: "2026-04-17",
        result_metrics: null,
        error_message: null,
        created_at: "2026-07-20T10:00:00Z",
        completed_at: null,
      }),
    );
    await userEvent.click(screen.getByRole("button", { name: /^Duplicate / }));

    const dialog = await screen.findByRole("dialog");
    // Prefilled from the source configuration, exactly.
    expect(within(dialog).getByLabelText("A distance")).toHaveValue("0.06");
    expect(within(dialog).getByLabelText("Initial shares")).toHaveValue("10000");

    const gridStep = within(dialog).getByLabelText("Grid step");
    await userEvent.clear(gridStep);
    await userEvent.type(gridStep, "0.02");

    queueResponse("/api/backtests/5/duplicate", () =>
      jsonResponse({ id: 11, status: "COMPLETED", name: "duplicate" }, 201),
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Run backtest" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/history/11"));
    const duplicateCall = fetchMock.mock.calls.find((call) =>
      String(call[0]).endsWith("/duplicate"),
    );
    const body = JSON.parse(String((duplicateCall![1] as RequestInit).body));
    expect(Object.keys(body)).toEqual(["configuration_overrides"]);
    expect(body.configuration_overrides.grid_step).toEqual({
      mode: "FIXED",
      value: "0.02",
    });
    // Untouched fields keep their exact source strings.
    expect(body.configuration_overrides.a_distance).toEqual({
      mode: "FIXED",
      value: "0.06",
    });
    // The create endpoint is never used as a fallback.
    expect(backtestListCalls().every((call) => (call[1] as RequestInit).method !== "POST")).toBe(
      true,
    );
  });
});

describe("compare page", () => {
  it("blocks fewer than two ids without calling the API", async () => {
    render(
      <AuthProvider>
        <CompareResults ids={[5]} />
      </AuthProvider>,
    );
    expect(await screen.findByText("Select at least two backtests")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter((call) => String(call[0]).includes("compare")),
    ).toHaveLength(0);
  });

  it("renders one column per run in request order", async () => {
    queueResponse("/api/backtests/compare", () =>
      jsonResponse({
        runs: [
          {
            id: 9,
            name: "first",
            result_metrics: { metrics: { strategy: { final_equity: "107771.70000000" } } },
          },
          { id: 3, name: "second", result_metrics: null },
        ],
      }),
    );
    render(
      <AuthProvider>
        <CompareResults ids={[9, 3]} />
      </AuthProvider>,
    );

    const table = await screen.findByRole("table");
    const headers = within(table).getAllByRole("columnheader");
    expect(headers[1]).toHaveTextContent("first (ID 9)");
    expect(headers[2]).toHaveTextContent("second (ID 3)");
    expect(within(table).getByText("107771.70000000")).toBeInTheDocument();
    // A null-metrics run stays a valid column.
    expect(within(table).getAllByText("—").length).toBeGreaterThan(0);
  });

  it("computes no ranking or difference", async () => {
    queueResponse("/api/backtests/compare", () =>
      jsonResponse({
        runs: [
          { id: 1, name: "a", result_metrics: { metrics: { strategy: { final_equity: "100" } } } },
          { id: 2, name: "b", result_metrics: { metrics: { strategy: { final_equity: "200" } } } },
        ],
      }),
    );
    render(
      <AuthProvider>
        <CompareResults ids={[1, 2]} />
      </AuthProvider>,
    );
    await screen.findByRole("table");

    // Scoped to the table: the page's own disclaimer legitimately uses the
    // word "ranking" to say it does none.
    const table = screen.getByRole("table");
    expect(table.textContent).not.toMatch(/winner|best|worst|rank|\+100|%\s*better/i);
    // Only the two stored values appear; no derived difference is shown.
    expect(table.textContent).toContain("100");
    expect(table.textContent).toContain("200");
    expect(table.textContent).not.toContain("+100");
    expect(screen.getByText(/no ranking, difference, or percentage change/i)).toBeInTheDocument();
  });

  it("shows the all-or-nothing 404 without naming an id", async () => {
    queueResponse("/api/backtests/compare", () =>
      jsonResponse(
        { error: { code: "BACKTEST_NOT_FOUND", message: "Backtest not found." } },
        404,
      ),
    );
    render(
      <AuthProvider>
        <CompareResults ids={[1, 999]} />
      </AuthProvider>,
    );

    expect(await screen.findByText("Comparison unavailable")).toBeInTheDocument();
    expect(screen.getByText("Backtest not found.")).toBeInTheDocument();
  });
});
