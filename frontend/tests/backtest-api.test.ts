import { beforeEach, describe, expect, it, vi } from "vitest";

import type { BacktestCreateRequest } from "@/lib/api/backtest-types";
import { createBacktest, getBacktest } from "@/lib/api/backtests";
import { ApiClientError } from "@/lib/api/errors";
import { serializeConfiguration } from "@/lib/backtests/configuration-state";
import { defaultConfiguration } from "@/lib/backtests/defaults";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function request(): BacktestCreateRequest {
  return {
    dataset_id: 7,
    configuration: serializeConfiguration(defaultConfiguration(), "OHLCV"),
  };
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

function lastInit(): RequestInit {
  return fetchMock.mock.calls[0][1] as RequestInit;
}

function sentBody(): Record<string, unknown> {
  return JSON.parse(String(lastInit().body));
}

describe("createBacktest request shape", () => {
  it("posts to /api/backtests with only the accepted top-level fields", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, status: "COMPLETED" }, 201));
    await createBacktest(request());

    expect(fetchMock.mock.calls[0][0]).toBe("/api/backtests");
    expect(lastInit().method).toBe("POST");
    expect(Object.keys(sentBody()).sort()).toEqual(["configuration", "dataset_id"]);
  });

  it("sends exactly the backend configuration keys and no others", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, status: "COMPLETED" }, 201));
    await createBacktest(request());

    const configuration = sentBody().configuration as Record<string, unknown>;
    expect(Object.keys(configuration).sort()).toEqual([
      "a_distance",
      "baseline",
      "buy_commission",
      "c_distance",
      "grid_step",
      "initial_cash",
      "initial_shares",
      "lot_size",
      "ohlc_path_mode",
      "risk_free_rate_annual",
      "sell_commission",
      "slippage",
      "tick_size",
      "trade_lots",
    ]);
  });

  it("never sends server-owned or dataset-wizard fields", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, status: "COMPLETED" }, 201));
    await createBacktest(request());

    const raw = String(lastInit().body);
    for (const forbidden of [
      "user_id",
      "status",
      "result_metrics",
      "events",
      "trades",
      "daily_equity",
      "event_equity",
      "preview_token",
      "price_bars",
    ]) {
      expect(raw).not.toContain(forbidden);
    }
  });

  it("keeps every decimal value as a JSON string", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, status: "COMPLETED" }, 201));
    await createBacktest(request());

    const configuration = sentBody().configuration as Record<string, never>;
    for (const key of ["initial_cash", "risk_free_rate_annual"] as const) {
      expect(typeof configuration[key]).toBe("string");
    }
    for (const key of ["a_distance", "c_distance", "grid_step"] as const) {
      expect(typeof (configuration[key] as { value: unknown }).value).toBe("string");
    }
    // Integer counts are strings too, so nothing passes through a float.
    for (const key of ["initial_shares", "lot_size", "trade_lots"] as const) {
      expect(typeof configuration[key]).toBe("string");
    }
    // No bare JSON number appears anywhere inside the configuration document.
    // (`dataset_id` at the top level is an id, not a financial value.)
    expect(JSON.stringify(configuration)).not.toMatch(/:\s*-?\d+(\.\d+)?\s*[,}]/);
  });

  it("preserves a null baseline rather than omitting it", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, status: "COMPLETED" }, 201));
    await createBacktest(request());

    const configuration = sentBody().configuration as Record<string, unknown>;
    expect(configuration).toHaveProperty("baseline");
    expect(configuration.baseline).toBeNull();
  });

  it("propagates an AbortSignal", async () => {
    const controller = new AbortController();
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, status: "COMPLETED" }, 201));
    await createBacktest(request(), controller.signal);
    expect(lastInit().signal).toBe(controller.signal);
  });

  it("sends no Authorization header", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1, status: "COMPLETED" }, 201));
    await createBacktest(request());
    const headers = new Headers((lastInit().headers ?? {}) as HeadersInit);
    expect(headers.has("authorization")).toBe(false);
    expect(headers.get("content-type")).toBe("application/json");
  });
});

describe("createBacktest responses", () => {
  it("parses a COMPLETED 201", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          id: 501,
          status: "COMPLETED",
          name: "159825 — A Grid 1% — 2026-07-20",
          created_at: "2026-07-20T10:00:00Z",
          completed_at: "2026-07-20T10:00:03Z",
          error_message: null,
          result_metrics: { metrics: { strategy: { final_equity: "107771.70000000" } } },
        },
        201,
      ),
    );
    const response = await createBacktest(request());
    expect(response.status).toBe("COMPLETED");
    expect(response.id).toBe(501);
    expect(response.error_message).toBeNull();
  });

  it("parses a FAILED 201 as a successful response, not an error", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          id: 502,
          status: "FAILED",
          name: "run",
          created_at: "2026-07-20T10:00:00Z",
          completed_at: "2026-07-20T10:00:01Z",
          error_message: "Sanitized description of the engine failure.",
          result_metrics: null,
        },
        201,
      ),
    );
    // Resolves rather than throwing: the run row was created.
    const response = await createBacktest(request());
    expect(response.status).toBe("FAILED");
    expect(response.result_metrics).toBeNull();
    expect(response.error_message).toBe("Sanitized description of the engine failure.");
  });

  it("preserves a 422 configuration error with its details", async () => {
    fetchMock.mockResolvedValue(
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
    const error = (await createBacktest(request()).catch((e: unknown) => e)) as ApiClientError;
    expect(error).toBeInstanceOf(ApiClientError);
    expect(error.status).toBe(422);
    expect(error.code).toBe("INVALID_ZONE_CONFIG");
    expect(error.details).toEqual({
      field: "configuration.c_distance",
      reason: "C <= A",
    });
  });

  it("preserves a 404 DATASET_NOT_FOUND", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: "DATASET_NOT_FOUND", message: "Dataset not found." } },
        404,
      ),
    );
    const error = (await createBacktest(request()).catch((e: unknown) => e)) as ApiClientError;
    expect(error.code).toBe("DATASET_NOT_FOUND");
    expect(error.status).toBe(404);
  });

  it("never retries a failed create", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: "UNEXPECTED_ERROR", message: "boom" } }, 500),
    );
    await createBacktest(request()).catch(() => undefined);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("never retries a network failure", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await createBacktest(request()).catch(() => undefined);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("getBacktest", () => {
  it("requests one run without any result-series include", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 501, status: "COMPLETED" }));
    await getBacktest(501);

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toBe("/api/backtests/501");
    expect(url).not.toContain("include");
    expect(lastInit().method).toBe("GET");
  });

  it("propagates an AbortSignal", async () => {
    const controller = new AbortController();
    fetchMock.mockResolvedValue(jsonResponse({ id: 501 }));
    await getBacktest(501, { signal: controller.signal });
    expect(lastInit().signal).toBe(controller.signal);
  });

  it("preserves a 404 for a missing or unowned run", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: "BACKTEST_NOT_FOUND", message: "Backtest not found." } },
        404,
      ),
    );
    const error = (await getBacktest(999).catch((e: unknown) => e)) as ApiClientError;
    expect(error.code).toBe("BACKTEST_NOT_FOUND");
  });
});

describe("configuration serialization", () => {
  it("sends the shared slippage shape without buy/sell", () => {
    const configuration = serializeConfiguration(defaultConfiguration(), "OHLCV");
    expect(configuration.slippage).toEqual({
      shared: true,
      mode: "FIXED",
      value: "0.001",
    });
    expect(configuration.slippage).not.toHaveProperty("buy");
    expect(configuration.slippage).not.toHaveProperty("sell");
  });

  it("sends the separate slippage shape without top-level mode/value", () => {
    const state = defaultConfiguration();
    state.slippage.shared = false;
    state.slippage.buy = { mode: "PERCENT", value: "0.002" };
    state.slippage.sell = { mode: "FIXED", value: "0.003" };

    const configuration = serializeConfiguration(state, "OHLCV");
    expect(configuration.slippage).toEqual({
      shared: false,
      buy: { mode: "PERCENT", value: "0.002" },
      sell: { mode: "FIXED", value: "0.003" },
    });
    expect(configuration.slippage).not.toHaveProperty("mode");
    expect(configuration.slippage).not.toHaveProperty("value");
  });

  it("sends a disabled tick size as enabled:false with a null value", () => {
    const configuration = serializeConfiguration(defaultConfiguration(), "OHLCV");
    expect(configuration.tick_size).toEqual({ enabled: false, value: null });
  });

  it("sends an enabled tick size with its exact string", () => {
    const state = defaultConfiguration();
    state.tick_size_enabled = true;
    state.tick_size_value = "0.001";
    expect(serializeConfiguration(state, "OHLCV").tick_size).toEqual({
      enabled: true,
      value: "0.001",
    });
  });

  it("omits the path mode for a close-only dataset", () => {
    const state = defaultConfiguration();
    state.ohlc_path_mode = "HIGH_FIRST";
    expect(serializeConfiguration(state, "CLOSE_ONLY").ohlc_path_mode).toBeNull();
    expect(serializeConfiguration(state, "OHLCV").ohlc_path_mode).toBe("HIGH_FIRST");
  });

  it("trims a baseline but preserves its exact digits", () => {
    const state = defaultConfiguration();
    state.baseline = "  0.63900000  ";
    expect(serializeConfiguration(state, "OHLCV").baseline).toBe("0.63900000");
  });

  it("always sends all six commission fields, enabled or not", () => {
    const configuration = serializeConfiguration(defaultConfiguration(), "OHLCV");
    expect(Object.keys(configuration.buy_commission).sort()).toEqual([
      "fixed",
      "fixed_enabled",
      "minimum",
      "minimum_enabled",
      "rate",
      "rate_enabled",
    ]);
  });
});
