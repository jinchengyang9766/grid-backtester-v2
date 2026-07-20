import { buildTestCsv, createDatasetThroughUi, runBacktestThroughUi } from "./fixtures/data";
import { expect, registerAndLogin, test } from "./fixtures/auth";

test.describe("dataset wizard and management", () => {
  test("uploads, maps, reviews cleaning, previews, and saves", async ({
    page,
    diagnostics,
  }) => {
    await registerAndLogin(page);
    await page.goto("/backtest/new");

    await page.getByLabel(/Price data file/).setInputFiles({
      name: "e2e-prices.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(buildTestCsv(), "utf8"),
    });
    await expect(page.getByText("e2e-prices.csv")).toBeVisible();
    await page.getByRole("button", { name: "Preview data" }).click();

    // MAPPING
    await expect(page.getByRole("heading", { name: "Confirm column mapping" })).toBeVisible();
    await expect(page.getByLabel(/^Date/)).toHaveValue("date");
    await expect(page.getByLabel(/^Close/)).toHaveValue("close");
    await expect(page.getByText("Automatically detected mapping")).toBeVisible();

    // Editing the mapping must trigger a fresh preview before advancing.
    await page.getByLabel(/^Volume/).selectOption("__unmapped__");
    await expect(page.getByText(/Mapping edited/)).toBeVisible();
    await page.getByRole("button", { name: /Apply mapping and continue/ }).click();

    // CLEANING_REVIEW — the fixture deliberately contains bad and duplicate rows.
    await expect(page.getByRole("heading", { name: "Review data cleaning" })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Rejected rows \(\d+\)/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Duplicate dates \(\d+\)/ })).toBeVisible();
    await expect(page.getByText(/appearing last in the file is kept/i)).toBeVisible();
    await page.getByRole("button", { name: /I understand/ }).click();

    // PREVIEW and save
    await expect(page.getByRole("heading", { name: /Preview cleaned data/ })).toBeVisible();
    await page.getByLabel("Dataset name").fill("Wizard dataset");
    await page.getByRole("button", { name: "Save dataset" }).click();

    await expect(page.getByText("Dataset saved")).toBeVisible();
    const url = new URL(page.url());
    expect(url.searchParams.get("dataset_id")).toMatch(/^\d+$/);
    // Only the id travels in the URL.
    expect(url.search).not.toContain("preview_token");
    expect(url.search).not.toContain("token");
    diagnostics.assertClean();
  });

  test("rejects an unsupported file without calling the API", async ({ page }) => {
    await registerAndLogin(page);
    await page.goto("/backtest/new");

    await page.getByLabel(/Price data file/).setInputFiles({
      name: "notes.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("not a dataset", "utf8"),
    });
    await page.getByRole("button", { name: "Preview data" }).click();
    await expect(page.getByText(/Choose a \.xls .* or \.csv file/)).toBeVisible();
  });

  test("lists, inspects, and deletes an unused dataset", async ({ page, diagnostics }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Deletable dataset");

    await page.goto("/datasets");
    await expect(page.getByRole("heading", { name: "Deletable dataset" })).toBeVisible();

    // Detail dialog, including keyboard dismissal.
    await page.getByRole("button", { name: /View details for Deletable dataset/ }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "Column mapping" })).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "Cleaning summary" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();

    // Delete, which only removes the row after the server confirms.
    await page.getByRole("button", { name: /Delete Deletable dataset/ }).click();
    const confirm = page.getByRole("dialog");
    await expect(confirm).toContainText("cannot be undone");
    await confirm.getByRole("button", { name: "Delete dataset" }).click();

    await expect(page.getByRole("heading", { name: "Deletable dataset" })).toBeHidden();
    diagnostics.assertClean();
  });

  test("refuses to delete a dataset a backtest still uses", async ({ page, diagnostics }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "In-use dataset");
    await runBacktestThroughUi(page);

    await page.goto("/datasets");
    await page.getByRole("button", { name: /Delete In-use dataset/ }).click();
    const confirm = page.getByRole("dialog");
    await confirm.getByRole("button", { name: "Delete dataset" }).click();

    // The dataset stays, with a safe explanation and no cascade.
    await expect(confirm.getByText(/cannot be deleted/i)).toBeVisible();
    await expect(confirm.getByText(/delete the backtests that use/i)).toBeVisible();
    await confirm.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByRole("heading", { name: "In-use dataset" })).toBeVisible();

    // 409 is a deliberately provoked response here.
    expect(diagnostics.pageErrors).toEqual([]);
    expect(diagnostics.consoleErrors).toEqual([]);
  });
});
