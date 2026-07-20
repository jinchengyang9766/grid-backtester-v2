import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DatasetList } from "@/components/datasets/dataset-list";
import { ExistingDatasetHandoff } from "@/components/upload/existing-dataset-handoff";
import { AuthProvider } from "@/lib/auth/auth-context";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/datasets",
}));

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const AUTH_OK = { id: 1, email: "owner@example.com" };

function summary(overrides: Record<string, unknown> = {}) {
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
    ...overrides,
  };
}

function detail(overrides: Record<string, unknown> = {}) {
  return {
    ...summary(),
    column_mapping: {
      date: "时间",
      open: "开盘",
      high: "最高",
      low: "最低",
      close: "收盘",
      volume: "成交量",
    },
    cleaning_summary: {
      total_rows_parsed: 422,
      valid_rows: 421,
      bad_rows: 1,
      duplicate_dates: 1,
      final_row_count: 420,
      date_range: { start: "2024-07-23", end: "2026-04-17" },
      data_mode: "OHLCV",
      bad_row_reasons: { NON_POSITIVE_PRICE: 1 },
    },
    ...overrides,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;

/**
 * Queued responses per path. Child effects run before parent effects, so the
 * list request can precede the provider's /api/auth/me — routing by URL keeps
 * these tests independent of that ordering.
 */
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
    return Promise.resolve(jsonResponse({ items: [] }));
  });
  vi.stubGlobal("fetch", fetchMock);
});

function callsTo(path: string) {
  return fetchMock.mock.calls.filter((call) => String(call[0]) === path);
}

async function renderList(items: unknown[] = [summary()]) {
  queueResponse("/api/datasets", () => jsonResponse({ items }));
  render(
    <AuthProvider>
      <DatasetList />
    </AuthProvider>,
  );
  await waitFor(() => expect(callsTo("/api/datasets")).toHaveLength(1));
}

describe("list states", () => {
  it("shows a loading state first", async () => {
    queueResponse("/api/datasets", () => new Promise<Response>(() => {}));
    render(
      <AuthProvider>
        <DatasetList />
      </AuthProvider>,
    );
    expect(await screen.findByText("Loading datasets…")).toBeInTheDocument();
  });

  it("renders every summary field, including Chinese metadata", async () => {
    await renderList();
    expect(await screen.findByText("农业ETF富国 159825")).toBeInTheDocument();
    expect(screen.getByText("农业ETF富国")).toBeInTheDocument();
    expect(screen.getByText("159825")).toBeInTheDocument();
    expect(screen.getByText("TongdaXin text export (.xls)")).toBeInTheDocument();
    expect(screen.getByText("159825.xls")).toBeInTheDocument();
    expect(screen.getByText("2024-07-23 to 2026-04-17")).toBeInTheDocument();
    expect(screen.getByText("420")).toBeInTheDocument();
    expect(screen.getByText("2026-07-20 10:30")).toBeInTheDocument();
  });

  it("shows an empty state that points to the upload page", async () => {
    await renderList([]);
    expect(await screen.findByText("No datasets yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload price data" })).toHaveAttribute(
      "href",
      "/backtest/new",
    );
  });

  it("shows an error with a working retry", async () => {
    queueResponse("/api/datasets", () => {
      throw new TypeError("Failed to fetch");
    });
    render(
      <AuthProvider>
        <DatasetList />
      </AuthProvider>,
    );
    expect(await screen.findByText("Could not load your datasets")).toBeInTheDocument();

    queueResponse("/api/datasets", () => jsonResponse({ items: [summary()] }));
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("农业ETF富国 159825")).toBeInTheDocument();
  });

  it("offers no rename or edit control", async () => {
    await renderList();
    await screen.findByText("农业ETF富国 159825");
    expect(screen.queryByRole("button", { name: /rename|edit/i })).not.toBeInTheDocument();
  });

  it("links each dataset to the backtest handoff by id", async () => {
    await renderList();
    await screen.findByText("农业ETF富国 159825");
    expect(
      screen.getByRole("link", { name: /Use 农业ETF富国 159825 for a backtest/ }),
    ).toHaveAttribute("href", "/backtest/new?dataset_id=7");
  });
});

describe("detail panel", () => {
  it("performs one request and shows the mapping and cleaning summary", async () => {
    await renderList();
    await screen.findByText("农业ETF富国 159825");

    queueResponse("/api/datasets/7", () => jsonResponse(detail()));
    await userEvent.click(screen.getByRole("button", { name: /View details/ }));

    const dialog = await screen.findByRole("dialog");
    expect(callsTo("/api/datasets/7")).toHaveLength(1);
    expect(within(dialog).getByText("时间")).toBeInTheDocument();
    expect(within(dialog).getByText("成交量")).toBeInTheDocument();
    expect(within(dialog).getByText("Non positive price")).toBeInTheDocument();
    expect(within(dialog).getByText("422")).toBeInTheDocument();
  });

  it("never shows price bars or a user id", async () => {
    await renderList();
    await screen.findByText("农业ETF富国 159825");
    queueResponse("/api/datasets/7", () => jsonResponse(detail()));
    await userEvent.click(screen.getByRole("button", { name: /View details/ }));

    const dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).not.toMatch(/price_?bars/i);
    expect(dialog.textContent).not.toMatch(/user_?id/i);
  });

  it("labels unmapped canonical fields rather than omitting them", async () => {
    await renderList();
    await screen.findByText("农业ETF富国 159825");
    queueResponse("/api/datasets/7", () =>
      jsonResponse(detail({ column_mapping: { date: "时间", close: "收盘" } })),
    );
    await userEvent.click(screen.getByRole("button", { name: /View details/ }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getAllByText("Not mapped").length).toBe(4);
  });

  it("shows a retryable error when the detail request fails", async () => {
    await renderList();
    await screen.findByText("农业ETF富国 159825");
    queueResponse("/api/datasets/7", () =>
      jsonResponse(
        { error: { code: "DATASET_NOT_FOUND", message: "Dataset not found." } },
        404,
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: /View details/ }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Dataset not found.")).toBeInTheDocument();
  });

  it("ignores a stale detail response for a previously selected dataset", async () => {
    await renderList([summary(), summary({ id: 8, name: "Second dataset" })]);
    await screen.findByText("Second dataset");

    // First click stays pending.
    let resolveStale: ((value: Response) => void) | undefined;
    queueResponse(
      "/api/datasets/7",
      () => new Promise<Response>((r) => (resolveStale = r)),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /View details for 农业ETF富国 159825/ }),
    );

    // Second click supersedes it and resolves first.
    queueResponse("/api/datasets/8", () =>
      jsonResponse(detail({ id: 8, name: "Second dataset" })),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /View details for Second dataset/ }),
    );
    await screen.findByRole("dialog");
    await waitFor(() =>
      expect(within(screen.getByRole("dialog")).getByText("时间")).toBeInTheDocument(),
    );

    // The stale response must not replace the newer selection.
    resolveStale?.(jsonResponse(detail({ id: 7, name: "农业ETF富国 159825" })));
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(
      within(screen.getByRole("dialog")).getByRole("heading", { name: "Second dataset" }),
    ).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    await renderList();
    await screen.findByText("农业ETF富国 159825");
    queueResponse("/api/datasets/7", () => jsonResponse(detail()));
    await userEvent.click(screen.getByRole("button", { name: /View details/ }));
    await screen.findByRole("dialog");

    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("deletion", () => {
  async function openDeleteDialog() {
    await renderList();
    await screen.findByText("农业ETF富国 159825");
    await userEvent.click(screen.getByRole("button", { name: /^Delete 农业ETF富国/ }));
    return screen.findByRole("dialog");
  }

  it("identifies the dataset and warns about consequences", async () => {
    const dialog = await openDeleteDialog();
    // Named in both the dialog description and the body copy.
    expect(within(dialog).getAllByText(/农业ETF富国 159825/).length).toBeGreaterThan(0);
    expect(within(dialog).getByText(/420 saved price rows/)).toBeInTheDocument();
    expect(within(dialog).getByText(/cannot be undone/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/refused while any saved backtest/i)).toBeInTheDocument();
    // No name-typing hoop.
    expect(within(dialog).queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("cancel performs no request and keeps the dataset", async () => {
    const dialog = await openDeleteDialog();
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(callsTo("/api/datasets/7")).toHaveLength(0);
    expect(screen.getByText("农业ETF富国 159825")).toBeInTheDocument();
  });

  it("confirm issues one DELETE and removes only the target", async () => {
    await renderList([summary(), summary({ id: 8, name: "Second dataset" })]);
    await screen.findByText("Second dataset");
    await userEvent.click(screen.getByRole("button", { name: /^Delete 农业ETF富国/ }));
    const dialog = await screen.findByRole("dialog");

    queueResponse("/api/datasets/7", () => new Response(null, { status: 204 }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete dataset" }));

    await waitFor(() =>
      expect(screen.queryByText("农业ETF富国 159825")).not.toBeInTheDocument(),
    );
    expect(callsTo("/api/datasets/7")).toHaveLength(1);
    expect(screen.getByText("Second dataset")).toBeInTheDocument();
  });

  it("prevents a double delete while pending", async () => {
    const dialog = await openDeleteDialog();
    let resolveDelete: ((value: Response) => void) | undefined;
    queueResponse(
      "/api/datasets/7",
      () => new Promise<Response>((r) => (resolveDelete = r)),
    );

    const button = within(dialog).getByRole("button", { name: /delete dataset|deleting/i });
    await userEvent.click(button);
    await waitFor(() => expect(button).toBeDisabled());
    await userEvent.click(button);

    expect(callsTo("/api/datasets/7")).toHaveLength(1);
    resolveDelete?.(new Response(null, { status: 204 }));
    await waitFor(() =>
      expect(screen.queryByText("农业ETF富国 159825")).not.toBeInTheDocument(),
    );
  });

  it("keeps the dataset and explains a 409 DATASET_IN_USE", async () => {
    const dialog = await openDeleteDialog();
    queueResponse("/api/datasets/7", () =>
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
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete dataset" }));

    expect(
      await within(screen.getByRole("dialog")).findByText(/cannot be deleted/i),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("dialog")).getByText(/delete the backtests that use/i),
    ).toBeInTheDocument();
    // Still listed, and no cascade was attempted.
    // The card itself is still listed: its link exists only on the card.
    expect(
      screen.getByRole("link", { name: /Use 农业ETF富国 159825 for a backtest/ }),
    ).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter((call) => String(call[0]).includes("/api/backtests")),
    ).toHaveLength(0);
  });

  it("drops a stale item neutrally on 404", async () => {
    const dialog = await openDeleteDialog();
    queueResponse("/api/datasets/7", () =>
      jsonResponse(
        { error: { code: "DATASET_NOT_FOUND", message: "Dataset not found." } },
        404,
      ),
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete dataset" }));

    await waitFor(() =>
      expect(screen.queryByText("农业ETF富国 159825")).not.toBeInTheDocument(),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps the dataset and allows retry after a network failure", async () => {
    const dialog = await openDeleteDialog();
    queueResponse("/api/datasets/7", () => {
      throw new TypeError("Failed to fetch");
    });
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete dataset" }));

    expect(
      await within(screen.getByRole("dialog")).findByText(/could not reach the server/i),
    ).toBeInTheDocument();
    // The card itself is still listed: its link exists only on the card.
    expect(
      screen.getByRole("link", { name: /Use 农业ETF富国 159825 for a backtest/ }),
    ).toBeInTheDocument();

    queueResponse("/api/datasets/7", () => new Response(null, { status: 204 }));
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Delete dataset" }),
    );
    await waitFor(() =>
      expect(screen.queryByText("农业ETF富国 159825")).not.toBeInTheDocument(),
    );
  });

  it("closes an open detail view for the deleted dataset", async () => {
    await renderList();
    await screen.findByText("农业ETF富国 159825");

    queueResponse("/api/datasets/7", () => jsonResponse(detail()));
    await userEvent.click(screen.getByRole("button", { name: /View details/ }));
    await screen.findByRole("dialog");
    await userEvent.keyboard("{Escape}");

    await userEvent.click(screen.getByRole("button", { name: /^Delete 农业ETF富国/ }));
    const deleteDialog = await screen.findByRole("dialog");
    queueResponse("/api/datasets/7", () => new Response(null, { status: 204 }));
    await userEvent.click(
      within(deleteDialog).getByRole("button", { name: "Delete dataset" }),
    );

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("existing dataset handoff", () => {
  it("loads an owned dataset and shows the saved state", async () => {
    queueResponse("/api/datasets/7", () => jsonResponse(detail()));
    render(
      <AuthProvider>
        <ExistingDatasetHandoff datasetId={7} />
      </AuthProvider>,
    );

    expect(await screen.findByText("Dataset saved")).toBeInTheDocument();
    expect(screen.getByText("农业ETF富国 159825")).toBeInTheDocument();
    expect(screen.getByText("420")).toBeInTheDocument();
    expect(callsTo("/api/datasets/7")).toHaveLength(1);
  });

  it("opens the strategy form from the saved handoff", async () => {
    queueResponse("/api/datasets/7", () => jsonResponse(detail()));
    render(
      <AuthProvider>
        <ExistingDatasetHandoff datasetId={7} />
      </AuthProvider>,
    );
    await screen.findByText("Dataset saved");

    // The form is not rendered until the user asks for it.
    expect(screen.queryByLabelText("Initial cash")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Configure strategy" }));
    expect(await screen.findByLabelText("Initial cash")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run backtest" })).toBeInTheDocument();
  });

  it("shows the safe backend message for a missing or unowned dataset", async () => {
    queueResponse("/api/datasets/999", () =>
      jsonResponse(
        { error: { code: "DATASET_NOT_FOUND", message: "Dataset not found." } },
        404,
      ),
    );
    render(
      <AuthProvider>
        <ExistingDatasetHandoff datasetId={999} />
      </AuthProvider>,
    );

    expect(await screen.findByText("Dataset unavailable")).toBeInTheDocument();
    expect(screen.getByText("Dataset not found.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to datasets" })).toHaveAttribute(
      "href",
      "/datasets",
    );
    // Nothing hints at whether someone else's dataset exists.
    const body = document.body.textContent ?? "";
    expect(body).not.toMatch(/belongs to|another user|not your/i);
  });
});
