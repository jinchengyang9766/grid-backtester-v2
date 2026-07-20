import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  compareBacktests,
  deleteBacktest,
  duplicateBacktest,
  getBacktestDetail,
  listBacktests,
  renameBacktest,
  rerunBacktest,
} from "@/lib/api/backtest-history";
import { ApiClientError } from "@/lib/api/errors";
import { serializeConfiguration } from "@/lib/backtests/configuration-state";
import { defaultConfiguration } from "@/lib/backtests/defaults";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

function url(): string {
  return String(fetchMock.mock.calls[0][0]);
}

function init(): RequestInit {
  return fetchMock.mock.calls[0][1] as RequestInit;
}

describe("listBacktests query serialization", () => {
  it("sends no query when nothing is filtered", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 20, offset: 0 }));
    await listBacktests({});
    expect(url()).toBe("/api/backtests");
  });

  it("omits an empty or whitespace-only search", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 20, offset: 0 }));
    await listBacktests({ search: "   " });
    expect(url()).toBe("/api/backtests");
  });

  it("trims a real search term", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 20, offset: 0 }));
    await listBacktests({ search: "  农业  " });
    expect(url()).toBe(`/api/backtests?${new URLSearchParams({ search: "农业" })}`);
  });

  it("uses the backend's exact filter names", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 20, offset: 0 }));
    await listBacktests({
      search: "grid",
      dataset_id: 7,
      status: "COMPLETED",
      limit: 20,
      offset: 40,
    });
    const params = new URL(url(), "http://localhost").searchParams;
    expect(params.get("search")).toBe("grid");
    expect(params.get("dataset_id")).toBe("7");
    expect(params.get("status")).toBe("COMPLETED");
    expect(params.get("limit")).toBe("20");
    expect(params.get("offset")).toBe("40");
  });

  it("parses a list response including null metrics and error messages", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        items: [
          {
            id: 5,
            dataset_id: 7,
            dataset_name: "农业ETF富国 159825",
            name: "failed run",
            status: "FAILED",
            start_date: "2024-07-23",
            end_date: "2026-04-17",
            ohlc_path_mode: null,
            created_at: "2026-07-20T10:00:00Z",
            completed_at: "2026-07-20T10:00:01Z",
            error_message: "Non-positive execution price.",
            result_metrics: null,
          },
        ],
        total: 1,
        limit: 20,
        offset: 0,
      }),
    );
    const response = await listBacktests({});
    expect(response.total).toBe(1);
    expect(response.items[0].result_metrics).toBeNull();
    expect(response.items[0].error_message).toBe("Non-positive execution price.");
    expect(response.items[0].dataset_name).toBe("农业ETF富国 159825");
  });

  it("propagates an AbortSignal", async () => {
    const controller = new AbortController();
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 20, offset: 0 }));
    await listBacktests({}, controller.signal);
    expect(init().signal).toBe(controller.signal);
  });
});

describe("getBacktestDetail", () => {
  it("serializes includes as one comma-separated parameter", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 5 }));
    await getBacktestDetail(5, {
      include: ["trades", "zone_events", "daily_equity", "event_equity"],
    });
    const params = new URL(url(), "http://localhost").searchParams;
    expect(params.get("include")).toBe("trades,zone_events,daily_equity,event_equity");
  });

  it("omits the parameter entirely when no series is requested", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 5 }));
    await getBacktestDetail(5);
    expect(url()).toBe("/api/backtests/5");
  });

  it("preserves decimal strings in every series", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        id: 5,
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
        ],
        daily_equity: [
          {
            id: 1,
            date: "2024-07-23",
            close: "0.63900000",
            cash: "100000",
            shares: 10000,
            equity: "106390.00000000",
            drawdown: "-0.01255742",
            zone_at_close: "IN_A",
          },
        ],
      }),
    );
    const detail = await getBacktestDetail(5, { include: ["trades", "daily_equity"] });
    expect(detail.trades?.[0].grid_price).toBe("0.65900000");
    expect(detail.trades?.[0].skip_reason).toBeNull();
    expect(detail.daily_equity?.[0].drawdown).toBe("-0.01255742");
    // Still strings, never parsed into numbers.
    expect(typeof detail.daily_equity?.[0].equity).toBe("string");
  });

  it("preserves an ownership-safe 404", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: "BACKTEST_NOT_FOUND", message: "Backtest not found." } },
        404,
      ),
    );
    const error = (await getBacktestDetail(9).catch((e: unknown) => e)) as ApiClientError;
    expect(error.code).toBe("BACKTEST_NOT_FOUND");
    expect(error.status).toBe(404);
  });
});

describe("write operations", () => {
  it("rename sends only a name", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 5, name: "renamed" }));
    await renameBacktest(5, "renamed");

    expect(url()).toBe("/api/backtests/5");
    expect(init().method).toBe("PATCH");
    const body = JSON.parse(String(init().body));
    expect(body).toEqual({ name: "renamed" });
    expect(Object.keys(body)).toEqual(["name"]);
  });

  it("rename preserves IMMUTABLE_FIELD", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: "IMMUTABLE_FIELD", message: "Only 'name' may be modified." } },
        422,
      ),
    );
    const error = (await renameBacktest(5, "x").catch((e: unknown) => e)) as ApiClientError;
    expect(error.code).toBe("IMMUTABLE_FIELD");
  });

  it("delete issues DELETE and resolves on 204", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(deleteBacktest(5)).resolves.toBeUndefined();
    expect(url()).toBe("/api/backtests/5");
    expect(init().method).toBe("DELETE");
  });

  it("rerun posts with no request body", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 6, status: "COMPLETED" }, 201));
    await rerunBacktest(5);

    expect(url()).toBe("/api/backtests/5/rerun");
    expect(init().method).toBe("POST");
    expect(init().body).toBeUndefined();
  });

  it("rerun parses a FAILED 201 as a created run", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          id: 6,
          status: "FAILED",
          name: "rerun",
          created_at: "2026-07-20T10:00:00Z",
          completed_at: "2026-07-20T10:00:01Z",
          error_message: "Non-positive execution price.",
          result_metrics: null,
        },
        201,
      ),
    );
    const created = await rerunBacktest(5);
    expect(created.status).toBe("FAILED");
    expect(created.id).toBe(6);
  });

  it("duplicate sends only configuration_overrides", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 7, status: "COMPLETED" }, 201));
    const configuration = serializeConfiguration(defaultConfiguration(), "OHLCV");
    await duplicateBacktest(5, configuration);

    expect(url()).toBe("/api/backtests/5/duplicate");
    const body = JSON.parse(String(init().body));
    expect(Object.keys(body)).toEqual(["configuration_overrides"]);
    expect(body.configuration_overrides.a_distance).toEqual({
      mode: "PERCENT",
      value: "0.05",
    });
    // Decimal values remain strings through the whole round trip.
    expect(typeof body.configuration_overrides.initial_cash).toBe("string");
  });

  it("compare sends the ids in the requested order", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ runs: [] }));
    await compareBacktests([9, 3, 5]);

    expect(url()).toBe("/api/backtests/compare");
    expect(JSON.parse(String(init().body))).toEqual({ backtest_ids: [9, 3, 5] });
  });

  it("compare preserves the all-or-nothing 404", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: "BACKTEST_NOT_FOUND", message: "Backtest not found." } },
        404,
      ),
    );
    const error = (await compareBacktests([1, 2]).catch((e: unknown) => e)) as ApiClientError;
    expect(error.code).toBe("BACKTEST_NOT_FOUND");
    // Never says which id failed.
    expect(error.message).not.toMatch(/\d/);
  });

  it("parses compare runs with null metrics", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        runs: [
          { id: 1, name: "ok", result_metrics: { metrics: { strategy: { final_equity: "1" } } } },
          { id: 2, name: "failed", result_metrics: null },
        ],
      }),
    );
    const response = await compareBacktests([1, 2]);
    expect(response.runs).toHaveLength(2);
    expect(response.runs[1].result_metrics).toBeNull();
  });
});

describe("transport rules", () => {
  it("never retries a failed write", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await renameBacktest(1, "x").catch(() => undefined);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fetchMock.mockClear();
    await deleteBacktest(1).catch(() => undefined);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fetchMock.mockClear();
    await rerunBacktest(1).catch(() => undefined);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fetchMock.mockClear();
    await compareBacktests([1, 2]).catch(() => undefined);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("never sends an Authorization header", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 20, offset: 0 }));
    await listBacktests({});
    await getBacktestDetail(1).catch(() => undefined);
    await renameBacktest(1, "x").catch(() => undefined);
    await rerunBacktest(1).catch(() => undefined);

    for (const call of fetchMock.mock.calls) {
      const headers = new Headers(((call[1] as RequestInit).headers ?? {}) as HeadersInit);
      expect(headers.has("authorization")).toBe(false);
    }
  });

  it("requests no export endpoint", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 20, offset: 0 }));
    await listBacktests({});
    await getBacktestDetail(1, { include: ["trades"] }).catch(() => undefined);
    for (const call of fetchMock.mock.calls) {
      expect(String(call[0])).not.toContain("/exports/");
    }
  });
});
