import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DatasetUploadWizard } from "@/components/upload/dataset-upload-wizard";
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

/** A realistic preview response shaped exactly like the backend's. */
function previewResponse(overrides: Record<string, unknown> = {}) {
  return {
    detected_format: "TDX_XLS",
    detected_encoding: "gb18030",
    auto_column_mapping: {
      date: "时间",
      open: "开盘",
      high: "最高",
      low: "最低",
      close: "收盘",
      volume: "成交量",
    },
    column_mapping_used: {
      date: "时间",
      open: "开盘",
      high: "最高",
      low: "最低",
      close: "收盘",
      volume: "成交量",
    },
    security_name: "农业ETF富国",
    security_code: "159825",
    data_mode: "OHLCV",
    preview_rows: [
      {
        date: "2024-07-23",
        open: "0.65100000",
        high: "0.65900000",
        low: "0.63800000",
        close: "0.63900000",
        volume: "1000",
      },
      {
        date: "2024-07-24",
        open: null,
        high: null,
        low: null,
        close: "0.64000000",
        volume: null,
      },
    ],
    bad_rows: [
      { row_number: 12, reason: "NON_POSITIVE_PRICE", raw: { 时间: "2024-08-01", 收盘: "0" } },
    ],
    duplicate_rows: [
      {
        date: "2024-09-02",
        kept_row_number: 41,
        discarded_row_number: 40,
        kept_raw: { 时间: "2024-09-02", 收盘: "0.70" },
        discarded_raw: { 时间: "2024-09-02", 收盘: "0.69" },
        reason: "KEEP_LAST",
      },
    ],
    cleaning_summary: {
      total_rows_parsed: 422,
      valid_rows: 421,
      bad_rows: 1,
      duplicate_dates: 1,
      final_row_count: 420,
      date_range: { start: "2024-07-23", end: "2026-04-17" },
      data_mode: "OHLCV",
      bad_row_reasons: { NON_POSITIVE_PRICE: 1, UNPARSEABLE_DATE: 0 },
    },
    preview_token: "token-A",
    ...overrides,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  replace.mockClear();
  fetchMock = vi.fn().mockResolvedValue(jsonResponse(AUTH_OK));
  vi.stubGlobal("fetch", fetchMock);
});

function makeFile(name = "159825.xls"): File {
  return new File(["时间\t收盘\n"], name, { type: "text/plain" });
}

function previewCalls() {
  return fetchMock.mock.calls.filter((call) =>
    String(call[0]).endsWith("/api/datasets/preview"),
  );
}

function saveCalls() {
  return fetchMock.mock.calls.filter((call) => String(call[0]) === "/api/datasets");
}

async function renderWizard() {
  render(
    <AuthProvider>
      <DatasetUploadWizard />
    </AuthProvider>,
  );
  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
}

async function selectFile(file = makeFile()) {
  const input = screen.getByLabelText(/price data file/i);
  await userEvent.upload(input, file);
}

/** Drive UPLOAD → MAPPING with a successful preview. */
async function reachMapping(response: unknown = previewResponse()) {
  await renderWizard();
  await selectFile();
  fetchMock.mockResolvedValueOnce(jsonResponse(response));
  await userEvent.click(screen.getByRole("button", { name: "Preview data" }));
  await screen.findByRole("heading", { name: "Confirm column mapping" });
}

describe("UPLOAD and DETECTING", () => {
  it("requires a file before previewing", async () => {
    await renderWizard();
    expect(screen.getByRole("button", { name: "Preview data" })).toBeDisabled();
    expect(previewCalls()).toHaveLength(0);
  });

  it("rejects an unsupported extension without calling the API", async () => {
    await renderWizard();
    // applyAccept:false simulates a file arriving past the accept filter
    // (drag-and-drop, or an "All files" picker), so the JS check is exercised.
    await userEvent.upload(screen.getByLabelText(/price data file/i), makeFile("prices.txt"), {
      applyAccept: false,
    });
    await userEvent.click(screen.getByRole("button", { name: "Preview data" }));

    expect(
      await screen.findByText(/choose a \.xls .* or \.csv file/i),
    ).toBeInTheDocument();
    expect(previewCalls()).toHaveLength(0);
  });

  it("the file input also restricts the picker to accepted extensions", async () => {
    await renderWizard();
    expect(screen.getByLabelText(/price data file/i)).toHaveAttribute(
      "accept",
      ".xls,.csv",
    );
  });

  it.each(["159825.xls", "159825.XLS", "prices.csv", "PRICES.CSV"])(
    "accepts %s",
    async (filename) => {
      await renderWizard();
      await selectFile(makeFile(filename));
      fetchMock.mockResolvedValueOnce(jsonResponse(previewResponse()));
      await userEvent.click(screen.getByRole("button", { name: "Preview data" }));

      await screen.findByRole("heading", { name: "Confirm column mapping" });
      expect(previewCalls()).toHaveLength(1);
    },
  );

  it("shows the selected file name and size", async () => {
    await renderWizard();
    await selectFile();
    expect(screen.getByText("159825.xls")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Replace file" })).toBeInTheDocument();
  });

  it("prevents a repeated preview click while pending", async () => {
    await renderWizard();
    await selectFile();
    let resolvePreview: ((value: Response) => void) | undefined;
    fetchMock.mockReturnValueOnce(new Promise<Response>((r) => (resolvePreview = r)));

    const button = screen.getByRole("button", { name: /preview data|reading file/i });
    await userEvent.click(button);
    await waitFor(() => expect(button).toBeDisabled());
    await userEvent.click(button);
    await userEvent.click(button);

    expect(previewCalls()).toHaveLength(1);

    resolvePreview?.(jsonResponse(previewResponse()));
    await screen.findByRole("heading", { name: "Confirm column mapping" });
  });

  it("shows an accessible backend error and stays on upload", async () => {
    await renderWizard();
    await selectFile();
    fetchMock.mockResolvedValueOnce(
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
    await userEvent.click(screen.getByRole("button", { name: "Preview data" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /only tongdaxin text-export/i,
    );
    expect(screen.getByRole("button", { name: "Preview data" })).toBeEnabled();
  });

  it("never renders a stack trace or raw HTML for a server failure", async () => {
    await renderWizard();
    await selectFile();
    fetchMock.mockResolvedValueOnce(
      new Response("<html><body>Traceback (most recent call last)</body></html>", {
        status: 500,
        headers: { "content-type": "text/html" },
      }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Preview data" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).not.toMatch(/traceback|<html>/i);
  });

  it("replacing the file clears the previous preview and returns to upload", async () => {
    await reachMapping();
    await userEvent.click(screen.getByRole("button", { name: "Back to upload" }));
    await selectFile(makeFile("other.csv"));

    // Old preview state is gone; no token from file A survives.
    expect(
      screen.queryByRole("heading", { name: "Confirm column mapping" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("other.csv")).toBeInTheDocument();
  });

  it("aborts the in-flight preview on unmount", async () => {
    const abortSpy = vi.fn();
    render(
      <AuthProvider>
        <DatasetUploadWizard />
      </AuthProvider>,
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await selectFile();

    fetchMock.mockImplementationOnce(
      (_url: string, init: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener("abort", () => {
            abortSpy();
            reject(new DOMException("Aborted", "AbortError"));
          });
        }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Preview data" }));

    // Unmounting the tree must cancel the request.
    screen.getByRole("button", { name: /reading file/i });
    const { unmount } = render(<div />);
    unmount();
  });
});

describe("MAPPING", () => {
  it("initialises the selectors from the mapping the backend used", async () => {
    await reachMapping();
    expect(screen.getByLabelText(/^Date/)).toHaveValue("时间");
    expect(screen.getByLabelText(/^Close/)).toHaveValue("收盘");
    expect(screen.getByLabelText(/^Volume/)).toHaveValue("成交量");
    expect(screen.getByText("Automatically detected mapping")).toBeInTheDocument();
  });

  it("shows preview metadata returned by the backend", async () => {
    await reachMapping();
    expect(screen.getByText("TDX_XLS")).toBeInTheDocument();
    expect(screen.getByText("gb18030")).toBeInTheDocument();
    expect(screen.getByText("农业ETF富国")).toBeInTheDocument();
    expect(screen.getByText("159825")).toBeInTheDocument();
  });

  it("never renders the preview token", async () => {
    const { container } = render(
      <AuthProvider>
        <DatasetUploadWizard />
      </AuthProvider>,
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await selectFile();
    fetchMock.mockResolvedValueOnce(jsonResponse(previewResponse()));
    await userEvent.click(screen.getByRole("button", { name: "Preview data" }));
    await screen.findByRole("heading", { name: "Confirm column mapping" });

    expect(container.innerHTML).not.toContain("token-A");
  });

  it("blocks continuing when a required field is unmapped", async () => {
    await reachMapping();
    await userEvent.selectOptions(screen.getByLabelText(/^Close/), "__unmapped__");

    expect(await screen.findByText("Close must be mapped.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /apply mapping/i })).toBeDisabled();
  });

  it("allows volume to be unmapped", async () => {
    await reachMapping();
    await userEvent.selectOptions(screen.getByLabelText(/^Volume/), "__unmapped__");
    expect(screen.getByRole("button", { name: /apply mapping/i })).toBeEnabled();
  });

  it("prevents a partial OHLC mapping", async () => {
    await reachMapping();
    await userEvent.selectOptions(screen.getByLabelText(/^High/), "__unmapped__");

    expect(
      await screen.findByText(/open, high, and low must be mapped together/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /apply mapping/i })).toBeDisabled();
  });

  it("prevents mapping one source column to two fields", async () => {
    await reachMapping();
    await userEvent.selectOptions(screen.getByLabelText(/^Open/), "收盘");

    // Reported against the later field: Open claims 收盘 first in field order,
    // so Close is the one flagged as the conflict. Shown both under the field
    // and in the summary, hence getAllByText.
    const conflicts = await screen.findAllByText(/收盘.*already mapped to Open/i);
    expect(conflicts.length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /apply mapping/i })).toBeDisabled();
  });

  it("advances without another request when the mapping is unchanged", async () => {
    await reachMapping();
    expect(previewCalls()).toHaveLength(1);

    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    await screen.findByRole("heading", { name: "Review data cleaning" });

    // The held token already describes this exact mapping.
    expect(previewCalls()).toHaveLength(1);
  });

  it("re-previews exactly once with the complete edited mapping", async () => {
    await reachMapping();
    await userEvent.selectOptions(screen.getByLabelText(/^Volume/), "__unmapped__");

    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        previewResponse({
          preview_token: "token-B",
          column_mapping_used: {
            date: "时间",
            open: "开盘",
            high: "最高",
            low: "最低",
            close: "收盘",
          },
        }),
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: /apply mapping/i }));
    await screen.findByRole("heading", { name: "Review data cleaning" });

    expect(previewCalls()).toHaveLength(2);
    const body = previewCalls()[1][1].body as FormData;
    const mapping = JSON.parse(String(body.get("manual_mapping")));
    // Complete mapping, with the cleared field sent as explicit null.
    expect(mapping).toEqual({
      date: "时间",
      open: "开盘",
      high: "最高",
      low: "最低",
      close: "收盘",
      volume: null,
    });
  });

  it("replaces the held token after a successful re-preview", async () => {
    await reachMapping();
    await userEvent.selectOptions(screen.getByLabelText(/^Volume/), "__unmapped__");
    fetchMock.mockResolvedValueOnce(
      jsonResponse(previewResponse({ preview_token: "token-B" })),
    );
    await userEvent.click(screen.getByRole("button", { name: /apply mapping/i }));
    await screen.findByRole("heading", { name: "Review data cleaning" });

    // Save must now use the replacement token, never the original.
    await userEvent.click(screen.getByRole("button", { name: /i understand/i }));
    await screen.findByRole("heading", { name: /preview cleaned data/i });
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 5, name: "n" }, 201));
    await userEvent.click(screen.getByRole("button", { name: "Save dataset" }));

    await waitFor(() => expect(saveCalls()).toHaveLength(1));
    expect(JSON.parse(String(saveCalls()[0][1].body)).preview_token).toBe("token-B");
  });

  it("stays on mapping when the re-preview fails", async () => {
    await reachMapping();
    await userEvent.selectOptions(screen.getByLabelText(/^Volume/), "__unmapped__");
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { error: { code: "MISSING_REQUIRED_COLUMN", message: "Date and Close must both be mapped." } },
        400,
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: /apply mapping/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Date and Close must both be mapped.",
    );
    expect(
      screen.getByRole("heading", { name: "Confirm column mapping" }),
    ).toBeInTheDocument();
    // The edited selection is retained for correction.
    expect(screen.getByLabelText(/^Volume/)).toHaveValue("__unmapped__");
  });

  it("a preview for a replaced file cannot revive the old state", async () => {
    await renderWizard();
    await selectFile(makeFile("file-a.xls"));

    // File A's preview is left in flight.
    let resolveStale: ((value: Response) => void) | undefined;
    fetchMock.mockReturnValueOnce(new Promise<Response>((r) => (resolveStale = r)));
    await userEvent.click(screen.getByRole("button", { name: "Preview data" }));

    // The user replaces the file before it returns.
    await selectFile(makeFile("file-b.csv"));
    expect(screen.getByText("file-b.csv")).toBeInTheDocument();

    // File A's response now lands. The generation guard must discard it, so
    // no token from file A can ever be used with file B selected.
    resolveStale?.(jsonResponse(previewResponse({ preview_token: "token-A" })));
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(
      screen.queryByRole("heading", { name: "Confirm column mapping" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preview data" })).toBeEnabled();
  });

  it("blocks a second re-preview while one is already in flight", async () => {
    await reachMapping();
    await userEvent.selectOptions(screen.getByLabelText(/^Volume/), "__unmapped__");

    let resolveRepreview: ((value: Response) => void) | undefined;
    fetchMock.mockReturnValueOnce(new Promise<Response>((r) => (resolveRepreview = r)));

    const button = screen.getByRole("button", { name: /apply mapping|re-reading/i });
    await userEvent.click(button);
    await waitFor(() => expect(button).toBeDisabled());
    await userEvent.click(button);

    expect(previewCalls()).toHaveLength(2);

    resolveRepreview?.(jsonResponse(previewResponse({ preview_token: "token-B" })));
    await screen.findByRole("heading", { name: "Review data cleaning" });
  });
});

describe("CLEANING_REVIEW", () => {
  async function reachCleaning() {
    await reachMapping();
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    await screen.findByRole("heading", { name: "Review data cleaning" });
  }

  it("shows the server's summary values exactly, including zeros", async () => {
    await reachCleaning();
    const summary = screen.getByRole("heading", { name: "Summary" }).parentElement!;
    expect(within(summary).getByText("422")).toBeInTheDocument();
    expect(within(summary).getByText("421")).toBeInTheDocument();
    expect(within(summary).getByText("420")).toBeInTheDocument();
    expect(screen.getByText("2024-07-23 to 2026-04-17")).toBeInTheDocument();
  });

  it("shows every bad-row reason count, including zero", async () => {
    await reachCleaning();
    const counts = screen
      .getByRole("heading", { name: "Rejected-row reasons" })
      .parentElement!;
    expect(within(counts).getByText("Non positive price")).toBeInTheDocument();
    // A zero count is listed rather than hidden.
    expect(within(counts).getByText("Unparseable date")).toBeInTheDocument();
    expect(within(counts).getByText("0")).toBeInTheDocument();
  });

  it("renders bad rows with their original values", async () => {
    await reachCleaning();
    const section = screen
      .getByRole("heading", { name: /Rejected rows \(1\)/ })
      .parentElement!;
    expect(within(section).getByText("12")).toBeInTheDocument();
    // Labelled cells, not a raw JSON dump.
    expect(within(section).getByText(/时间:/)).toBeInTheDocument();
    expect(within(section).getByText("2024-08-01")).toBeInTheDocument();
    expect(section.textContent).not.toContain('{"时间"');
  });

  it("renders duplicate rows and explains the keep-last policy", async () => {
    await reachCleaning();
    const section = screen
      .getByRole("heading", { name: /Duplicate dates \(1\)/ })
      .parentElement!;
    expect(within(section).getAllByText("2024-09-02").length).toBeGreaterThan(0);
    expect(within(section).getByText("Row 41")).toBeInTheDocument();
    expect(within(section).getByText("Row 40")).toBeInTheDocument();
    expect(
      screen.getByText(/the one appearing last in the file is kept/i),
    ).toBeInTheDocument();
  });

  it("shows empty states when there are no bad or duplicate rows", async () => {
    await reachMapping(
      previewResponse({
        bad_rows: [],
        duplicate_rows: [],
        cleaning_summary: {
          ...previewResponse().cleaning_summary,
          bad_rows: 0,
          duplicate_dates: 0,
          bad_row_reasons: {},
        },
      }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    await screen.findByRole("heading", { name: "Review data cleaning" });

    expect(screen.getByText("No rejected rows")).toBeInTheDocument();
    expect(screen.getByText("No duplicate dates")).toBeInTheDocument();
  });

  it("acknowledgement advances and back returns to mapping", async () => {
    await reachCleaning();
    await userEvent.click(screen.getByRole("button", { name: "Back to column mapping" }));
    expect(
      await screen.findByRole("heading", { name: "Confirm column mapping" }),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    await userEvent.click(screen.getByRole("button", { name: /i understand/i }));
    expect(
      await screen.findByRole("heading", { name: /preview cleaned data/i }),
    ).toBeInTheDocument();
  });
});

describe("PREVIEW and save", () => {
  async function reachPreview(response: unknown = previewResponse()) {
    await reachMapping(response);
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    await userEvent.click(screen.getByRole("button", { name: /i understand/i }));
    await screen.findByRole("heading", { name: /preview cleaned data/i });
  }

  it("renders normalized rows with decimal strings and neutral nulls", async () => {
    await reachPreview();
    expect(screen.getByText("0.63900000")).toBeInTheDocument();
    expect(screen.getByText("0.65100000")).toBeInTheDocument();
    // The second row's null OHLC/volume render as a dash, not "null".
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(4);
    expect(screen.queryByText("null")).not.toBeInTheDocument();
  });

  it("separates the saved row count from the previewed sample size", async () => {
    await reachPreview();
    expect(screen.getByText("420")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText(/bounded sample/i)).toBeInTheDocument();
  });

  it("prefills an editable name from the security metadata", async () => {
    await reachPreview();
    const nameInput = screen.getByLabelText("Dataset name");
    expect(nameInput).toHaveValue("农业ETF富国 159825");

    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "My dataset");
    expect(nameInput).toHaveValue("My dataset");
  });

  it("requires a non-blank name and does not call the API", async () => {
    await reachPreview();
    await userEvent.clear(screen.getByLabelText("Dataset name"));
    await userEvent.type(screen.getByLabelText("Dataset name"), "   ");
    await userEvent.click(screen.getByRole("button", { name: "Save dataset" }));

    expect(await screen.findByText("Enter a name for this dataset.")).toBeInTheDocument();
    expect(saveCalls()).toHaveLength(0);
  });

  it("trims the name and sends no column_mapping", async () => {
    await reachPreview();
    await userEvent.clear(screen.getByLabelText("Dataset name"));
    await userEvent.type(screen.getByLabelText("Dataset name"), "  Padded name  ");
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 42, name: "Padded name" }, 201));
    await userEvent.click(screen.getByRole("button", { name: "Save dataset" }));

    await waitFor(() => expect(saveCalls()).toHaveLength(1));
    const body = JSON.parse(String(saveCalls()[0][1].body));
    expect(body).toEqual({ name: "Padded name", preview_token: "token-A" });
    expect(body).not.toHaveProperty("column_mapping");
  });

  it("prevents a double save while pending", async () => {
    await reachPreview();
    let resolveSave: ((value: Response) => void) | undefined;
    fetchMock.mockReturnValueOnce(new Promise<Response>((r) => (resolveSave = r)));

    const button = screen.getByRole("button", { name: /save dataset|saving/i });
    await userEvent.click(button);
    await waitFor(() => expect(button).toBeDisabled());
    await userEvent.click(button);

    expect(saveCalls()).toHaveLength(1);
    resolveSave?.(jsonResponse({ id: 42, name: "n" }, 201));
    await screen.findByText("Dataset saved");
  });

  it("reaches DATASET_SAVED and navigates with only the dataset id", async () => {
    await reachPreview();
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          id: 42,
          name: "农业ETF富国 159825",
          data_mode: "OHLCV",
          start_date: "2024-07-23",
          end_date: "2026-04-17",
          row_count: 420,
          created_at: "2026-07-20T10:00:00Z",
        },
        201,
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: "Save dataset" }));

    expect(await screen.findByText("Dataset saved")).toBeInTheDocument();
    expect(replace).toHaveBeenCalledWith("/backtest/new?dataset_id=42");
    // The token must never appear in the URL.
    const url = String(replace.mock.calls[0][0]);
    expect(url).not.toContain("preview_token");
    expect(url).not.toContain("token-A");
  });

  it("shows the saved handoff without a strategy form", async () => {
    await reachPreview();
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          id: 42,
          name: "Saved set",
          data_mode: "OHLCV",
          start_date: "2024-07-23",
          end_date: "2026-04-17",
          row_count: 420,
          created_at: "2026-07-20T10:00:00Z",
        },
        201,
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: "Save dataset" }));
    await screen.findByText("Dataset saved");

    expect(screen.getByText("Saved set")).toBeInTheDocument();
    expect(screen.getByText("Coming next")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Configure strategy" })).toBeDisabled();
    // No strategy inputs exist yet.
    expect(screen.queryByLabelText(/initial cash/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/grid step/i)).not.toBeInTheDocument();
  });

  it("never calls a backtest endpoint", async () => {
    await reachPreview();
    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 42, name: "n" }, 201));
    await userEvent.click(screen.getByRole("button", { name: "Save dataset" }));
    await screen.findByText("Dataset saved");

    for (const call of fetchMock.mock.calls) {
      expect(String(call[0])).not.toContain("/api/backtests");
    }
  });

  it("offers a refresh when the preview token has expired", async () => {
    await reachPreview();
    fetchMock.mockResolvedValueOnce(
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
    await userEvent.click(screen.getByRole("button", { name: "Save dataset" }));

    expect(
      await screen.findByText("This preview is no longer available"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh preview" })).toBeInTheDocument();
    // Saving is blocked until a fresh token arrives; no silent retry happened.
    expect(screen.getByRole("button", { name: "Save dataset" })).toBeDisabled();
    expect(saveCalls()).toHaveLength(1);
  });

  it("refreshing replaces the token so the next save succeeds", async () => {
    await reachPreview();
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        { error: { code: "PREVIEW_TOKEN_NOT_FOUND", message: "Preview token not found or expired." } },
        404,
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: "Save dataset" }));
    await screen.findByRole("button", { name: "Refresh preview" });

    fetchMock.mockResolvedValueOnce(
      jsonResponse(previewResponse({ preview_token: "token-FRESH" })),
    );
    await userEvent.click(screen.getByRole("button", { name: "Refresh preview" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save dataset" })).toBeEnabled(),
    );

    fetchMock.mockResolvedValueOnce(jsonResponse({ id: 42, name: "n" }, 201));
    await userEvent.click(screen.getByRole("button", { name: "Save dataset" }));

    await waitFor(() => expect(saveCalls()).toHaveLength(2));
    expect(JSON.parse(String(saveCalls()[1][1].body)).preview_token).toBe("token-FRESH");
  });
});
