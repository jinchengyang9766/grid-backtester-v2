/**
 * Deterministic test data, generated at runtime.
 *
 * The CSV is built here rather than committed so no financial dataset lives
 * in the repository, and it is small enough that a full backtest completes in
 * well under a second.
 */

import { expect, type Page } from "@playwright/test";

/**
 * 30 close-only rows with one deliberately bad row (a non-positive price) and
 * one duplicate date, so the cleaning-review step has something real to show.
 */
export function buildTestCsv(): string {
  // Volume is included so the mapping step has an optional field that can be
  // genuinely unmapped; the dataset stays close-only either way.
  const lines = ["date,close,volume"];
  const start = new Date(Date.UTC(2024, 0, 1));
  for (let day = 0; day < 30; day += 1) {
    const date = new Date(start.getTime() + day * 86_400_000);
    // The cleaner accepts YYYY/MM/DD only; an ISO date is an unparseable date.
    const stamp = date.toISOString().slice(0, 10).replace(/-/g, "/");
    // A gentle zig-zag so the grid actually trades.
    const cents = 1000 + (day % 6) * 20 - (day % 4) * 10;
    lines.push(`${stamp},${(cents / 1000).toFixed(3)},${1000 + day * 10}`);
  }
  // One non-positive close (rejected) and one repeat of the last date, so the
  // cleaning review has a real rejected row and a real duplicate to show.
  lines.push("2024/02/01,0,1000");
  lines.push("2024/01/30,1.234,1500");
  return `${lines.join("\n")}\n`;
}

export const TEST_DATASET_ROWS = 30;

/** Upload the generated CSV and save it as a dataset, through the real UI. */
export async function createDatasetThroughUi(
  page: Page,
  name: string,
): Promise<number> {
  await page.goto("/backtest/new");

  await page.getByLabel(/Price data file/).setInputFiles({
    name: "e2e-prices.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(buildTestCsv(), "utf8"),
  });
  await page.getByRole("button", { name: "Preview data" }).click();

  await expect(page.getByRole("heading", { name: "Confirm column mapping" })).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByRole("heading", { name: "Review data cleaning" })).toBeVisible();
  await page.getByRole("button", { name: /I understand/ }).click();

  await expect(page.getByRole("heading", { name: /Preview cleaned data/ })).toBeVisible();
  const nameField = page.getByLabel("Dataset name");
  await nameField.fill(name);
  await page.getByRole("button", { name: "Save dataset" }).click();

  await expect(page.getByText("Dataset saved")).toBeVisible();
  await expect(page).toHaveURL(/dataset_id=\d+/);
  const datasetId = Number(new URL(page.url()).searchParams.get("dataset_id"));
  expect(datasetId).toBeGreaterThan(0);
  return datasetId;
}

/**
 * Configure and run a backtest from the saved-dataset handoff.
 * Returns the created run's id.
 */
export async function runBacktestThroughUi(page: Page): Promise<number> {
  await page.getByRole("button", { name: "Configure strategy" }).click();
  await expect(page.getByLabel("Initial cash")).toBeVisible();

  // A small, fast, deterministic configuration for this fixture.
  await page.getByLabel("Initial cash").fill("10000");
  await page.getByLabel("Initial shares").fill("1000");
  await page.getByLabel("Lot size").fill("100");
  await page.getByLabel("Trade lots").fill("1");
  await page.getByLabel("A distance mode").selectOption("FIXED");
  await page.getByLabel("A distance", { exact: true }).fill("0.05");
  await page.getByLabel("C distance mode").selectOption("FIXED");
  await page.getByLabel("C distance", { exact: true }).fill("0.10");
  await page.getByLabel("Grid step mode").selectOption("FIXED");
  await page.getByLabel("Grid step", { exact: true }).fill("0.01");

  await page.getByRole("button", { name: "Run backtest" }).click();
  await expect(page.getByText("Backtest completed")).toBeVisible({ timeout: 60_000 });
  await expect(page).toHaveURL(/backtest_id=\d+/);
  return Number(new URL(page.url()).searchParams.get("backtest_id"));
}
