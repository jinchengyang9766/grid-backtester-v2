/**
 * Real browser downloads for all four exports.
 *
 * Each file is written to Playwright's temporary directory, verified, and
 * deleted immediately — no export artifact ever reaches the repository.
 */

import { existsSync, readFileSync, rmSync } from "node:fs";
import { join } from "node:path";

import type { Download, Page } from "@playwright/test";

import { TEST_DATASET_ROWS, createDatasetThroughUi, runBacktestThroughUi } from "./fixtures/data";
import { expect, registerAndLogin, test } from "./fixtures/auth";

const REPO_ROOT = join(__dirname, "..", "..");

const TRADES_HEADER =
  "date,event_sequence,side,grid_price,execution_price,shares,notional," +
  "commission,slippage_cost,cash_after,shares_after,equity_after,status,skip_reason";
const EQUITY_HEADER = "backtest_run_id,date,close,cash,shares,equity,drawdown,zone_at_close";

async function download(page: Page, linkName: string): Promise<Download> {
  const [event] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: linkName }).click(),
  ]);
  return event;
}

/** Read a completed download, then delete the temporary file it produced. */
async function readAndDiscard(event: Download): Promise<Buffer> {
  const path = await event.path();
  if (path === null) throw new Error("download produced no file");
  const bytes = readFileSync(path);
  rmSync(path, { force: true });
  return bytes;
}

test.describe("export downloads", () => {
  test("downloads and verifies all four exports", async ({ page, diagnostics }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Export dataset");
    const backtestId = await runBacktestThroughUi(page);

    // Any *fetch* of an export would show up here. Native download navigations
    // deliberately do not, so this stays empty for the whole test — which is
    // exactly the point: rendering the page must not pull an export, and the
    // downloads below must not go through JavaScript. Each download's own URL
    // is asserted instead, straight off the Download object.
    const exportFetches: string[] = [];
    page.on("request", (request) => {
      const path = new URL(request.url()).pathname;
      if (path.includes("/exports/")) exportFetches.push(path);
    });

    await page.goto(`/history/${backtestId}`);
    await expect(page.getByRole("heading", { name: "Downloads" })).toBeVisible();
    expect(exportFetches, "nothing is generated before a link is activated").toEqual([]);

    const trades = await download(page, "Download trades CSV");
    expect(trades.suggestedFilename()).toBe(`backtest-${backtestId}-trades.csv`);
    expect(new URL(trades.url()).pathname).toBe(
      `/api/backtests/${backtestId}/exports/trades.csv`,
    );
    const tradeLines = (await readAndDiscard(trades)).toString("utf8").trimEnd().split("\n");
    expect(tradeLines[0]).toBe(TRADES_HEADER);
    expect(tradeLines.length, "the seeded run trades at least once").toBeGreaterThan(1);

    const equity = await download(page, "Download equity CSV");
    expect(equity.suggestedFilename()).toBe(`backtest-${backtestId}-equity.csv`);
    expect(new URL(equity.url()).pathname).toBe(
      `/api/backtests/${backtestId}/exports/equity.csv`,
    );
    const equityLines = (await readAndDiscard(equity)).toString("utf8").trimEnd().split("\n");
    expect(equityLines[0]).toBe(EQUITY_HEADER);
    // One row per cleaned trading day: the fixture's duplicate date collapses
    // and its invalid row is rejected, leaving exactly TEST_DATASET_ROWS.
    expect(equityLines.length - 1).toBe(TEST_DATASET_ROWS);

    const resultJson = await download(page, "Download complete result JSON");
    expect(resultJson.suggestedFilename()).toBe(`backtest-${backtestId}-result.json`);
    expect(new URL(resultJson.url()).pathname).toBe(
      `/api/backtests/${backtestId}/exports/result.json`,
    );
    const parsed: unknown = JSON.parse((await readAndDiscard(resultJson)).toString("utf8"));
    expect(Object.keys(parsed as Record<string, unknown>)).toEqual([
      "configuration",
      "result_metrics",
      "benchmark_1",
      "benchmark_2",
      "dataset_summary",
    ]);

    const pdf = await download(page, "Download PDF report");
    expect(pdf.suggestedFilename()).toBe(`backtest-${backtestId}-report.pdf`);
    expect(new URL(pdf.url()).pathname).toBe(
      `/api/backtests/${backtestId}/exports/report.pdf`,
    );
    const pdfBytes = await readAndDiscard(pdf);
    expect(pdfBytes.length).toBeGreaterThan(1000);
    expect(pdfBytes.subarray(0, 5).toString("latin1")).toBe("%PDF-");

    // Still empty: every file above arrived by native navigation, never fetch.
    expect(exportFetches, "exports must not be fetched by JavaScript").toEqual([]);

    diagnostics.assertClean();
  });

  test("links carry only the numeric id and stay same-origin", async ({ page }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Export link dataset");
    const backtestId = await runBacktestThroughUi(page);
    await page.goto(`/history/${backtestId}`);

    const links = page.getByRole("link", { name: /^Download/ });
    await expect(links).toHaveCount(4);

    const hrefs = await links.evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute("href") ?? ""),
    );
    for (const href of hrefs) {
      expect(href).toMatch(new RegExp(`^/api/backtests/${backtestId}/exports/`));
      expect(href).not.toMatch(/^https?:/);
      expect(href).not.toContain("token");
    }
  });

  test("no export artifact is written into the repository", async ({ page }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "No artifact dataset");
    const backtestId = await runBacktestThroughUi(page);
    await page.goto(`/history/${backtestId}`);

    await readAndDiscard(await download(page, "Download trades CSV"));

    for (const stray of [
      join(REPO_ROOT, `backtest-${backtestId}-trades.csv`),
      join(REPO_ROOT, "frontend", `backtest-${backtestId}-trades.csv`),
    ]) {
      expect(existsSync(stray), `${stray} must not exist`).toBe(false);
    }
  });
});
