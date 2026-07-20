import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  deleteDataset,
  getDataset,
  listDatasets,
  previewDataset,
  saveDataset,
} from "@/lib/api/datasets";
import type { ManualColumnMapping } from "@/lib/api/dataset-types";
import { ApiClientError } from "@/lib/api/errors";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function makeFile(name = "159825.xls"): File {
  return new File(["时间\t收盘\n2024-07-23\t0.639\n"], name, { type: "text/plain" });
}

const MAPPING: ManualColumnMapping = {
  date: "时间",
  open: "开盘",
  high: "最高",
  low: "最低",
  close: "收盘",
  volume: null,
};

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

function lastInit(): RequestInit {
  return fetchMock.mock.calls[0][1] as RequestInit;
}

describe("previewDataset", () => {
  it("sends multipart FormData containing the file", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ preview_token: "t" }));
    const file = makeFile();
    await previewDataset(file);

    expect(fetchMock.mock.calls[0][0]).toBe("/api/datasets/preview");
    const init = lastInit();
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    const body = init.body as FormData;
    expect(body.get("file")).toBe(file);
  });

  it("omits manual_mapping when none is supplied", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ preview_token: "t" }));
    await previewDataset(makeFile());
    expect((lastInit().body as FormData).has("manual_mapping")).toBe(false);
  });

  it("sends manual_mapping as one JSON string field", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ preview_token: "t" }));
    await previewDataset(makeFile(), MAPPING);

    const body = lastInit().body as FormData;
    const entries = [...body.keys()];
    // One field, not one multipart part per mapping entry.
    expect(entries.filter((key) => key === "manual_mapping")).toHaveLength(1);
    expect(entries).not.toContain("manual_mapping[date]");
    expect(entries).not.toContain("date");

    const raw = body.get("manual_mapping");
    expect(typeof raw).toBe("string");
    expect(JSON.parse(String(raw))).toEqual(MAPPING);
    // Unmapped fields travel as explicit null so the backend unmaps them.
    expect(JSON.parse(String(raw)).volume).toBeNull();
  });

  it("never sets Content-Type by hand, so the browser adds the boundary", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ preview_token: "t" }));
    await previewDataset(makeFile(), MAPPING);

    const headers = new Headers((lastInit().headers ?? {}) as HeadersInit);
    expect(headers.has("content-type")).toBe(false);
  });

  it("propagates an AbortSignal", async () => {
    const controller = new AbortController();
    fetchMock.mockResolvedValue(jsonResponse({ preview_token: "t" }));
    await previewDataset(makeFile(), undefined, controller.signal);
    expect(lastInit().signal).toBe(controller.signal);
  });

  it("preserves backend error codes", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: "UNSUPPORTED_FILE_TYPE",
            message:
              "Only TongdaXin text-export .xls files are supported, not binary spreadsheet files.",
          },
        },
        400,
      ),
    );
    const error = (await previewDataset(makeFile()).catch((e: unknown) => e)) as ApiClientError;
    expect(error).toBeInstanceOf(ApiClientError);
    expect(error.code).toBe("UNSUPPORTED_FILE_TYPE");
    expect(error.status).toBe(400);
  });

  it("does not retry a failed preview", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await previewDataset(makeFile()).catch(() => undefined);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("saveDataset", () => {
  it("sends only name and preview_token", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 1 }, 201));
    await saveDataset({ name: "My dataset", preview_token: "opaque-token" });

    expect(fetchMock.mock.calls[0][0]).toBe("/api/datasets");
    const body = JSON.parse(String(lastInit().body));
    expect(body).toEqual({ name: "My dataset", preview_token: "opaque-token" });
    // The backend forbids extras; the mapping is already bound to the token.
    expect(Object.keys(body).sort()).toEqual(["name", "preview_token"]);
    expect(body).not.toHaveProperty("column_mapping");
    expect(body).not.toHaveProperty("manual_mapping");
  });

  it("preserves PREVIEW_TOKEN_NOT_FOUND", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: "PREVIEW_TOKEN_NOT_FOUND",
            message: "Preview token not found or expired.",
          },
        },
        404,
      ),
    );
    const error = (await saveDataset({ name: "n", preview_token: "t" }).catch(
      (e: unknown) => e,
    )) as ApiClientError;
    expect(error.code).toBe("PREVIEW_TOKEN_NOT_FOUND");
    expect(error.status).toBe(404);
  });

  it("does not retry a failed save", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: "UNEXPECTED_ERROR", message: "boom" } }, 500),
    );
    await saveDataset({ name: "n", preview_token: "t" }).catch(() => undefined);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("listDatasets and getDataset", () => {
  it("parses the list response", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        items: [
          {
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
            created_at: "2026-07-20T10:00:00Z",
          },
        ],
      }),
    );
    const response = await listDatasets();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/datasets");
    expect(response.items).toHaveLength(1);
    expect(response.items[0].security_name).toBe("农业ETF富国");
    expect(response.items[0].row_count).toBe(420);
  });

  it("parses the detail response including mapping and cleaning summary", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        id: 7,
        name: "d",
        source_type: "TDX_XLS",
        original_filename: "159825.xls",
        security_name: null,
        security_code: null,
        data_mode: "OHLCV",
        start_date: "2024-07-23",
        end_date: "2026-04-17",
        row_count: 420,
        created_at: "2026-07-20T10:00:00Z",
        column_mapping: { date: "时间", close: "收盘" },
        cleaning_summary: { total_rows_parsed: 420, final_row_count: 420 },
      }),
    );
    const detail = await getDataset(7);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/datasets/7");
    expect(detail.column_mapping).toEqual({ date: "时间", close: "收盘" });
    expect(detail.cleaning_summary.final_row_count).toBe(420);
  });

  it("propagates an AbortSignal on detail requests", async () => {
    const controller = new AbortController();
    fetchMock.mockResolvedValue(jsonResponse({ id: 7 }));
    await getDataset(7, controller.signal);
    expect(lastInit().signal).toBe(controller.signal);
  });

  it("preserves DATASET_NOT_FOUND", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: "DATASET_NOT_FOUND", message: "Dataset not found." } },
        404,
      ),
    );
    const error = (await getDataset(999).catch((e: unknown) => e)) as ApiClientError;
    expect(error.code).toBe("DATASET_NOT_FOUND");
  });
});

describe("deleteDataset", () => {
  it("issues a DELETE and resolves on 204", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(deleteDataset(7)).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/datasets/7");
    expect(lastInit().method).toBe("DELETE");
  });

  it("preserves DATASET_IN_USE", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: "DATASET_IN_USE",
            message: "Dataset is referenced by existing resources and cannot be deleted.",
          },
        },
        409,
      ),
    );
    const error = (await deleteDataset(7).catch((e: unknown) => e)) as ApiClientError;
    expect(error.code).toBe("DATASET_IN_USE");
    expect(error.status).toBe(409);
  });

  it("does not retry a failed delete", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await deleteDataset(7).catch(() => undefined);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("transport rules", () => {
  it("never sends an Authorization header on any dataset request", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [] }));
    await listDatasets();
    await getDataset(1).catch(() => undefined);
    await deleteDataset(1).catch(() => undefined);
    await saveDataset({ name: "n", preview_token: "t" }).catch(() => undefined);
    await previewDataset(makeFile()).catch(() => undefined);

    for (const call of fetchMock.mock.calls) {
      const headers = new Headers(((call[1] as RequestInit).headers ?? {}) as HeadersInit);
      expect(headers.has("authorization")).toBe(false);
    }
  });

  it("uses same-origin credentials so the HttpOnly cookie is sent", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [] }));
    await listDatasets();
    expect(lastInit()).toMatchObject({ credentials: "same-origin" });
  });

  it("never logs the token or file contents", async () => {
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    fetchMock.mockResolvedValue(jsonResponse({ preview_token: "super-secret-token" }));

    await previewDataset(makeFile());
    await saveDataset({ name: "n", preview_token: "super-secret-token" }).catch(
      () => undefined,
    );

    expect(logSpy).not.toHaveBeenCalled();
    expect(errorSpy).not.toHaveBeenCalled();
  });
});
