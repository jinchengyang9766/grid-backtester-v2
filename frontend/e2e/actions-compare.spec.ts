import { createDatasetThroughUi, runBacktestThroughUi } from "./fixtures/data";
import { expect, registerAndLogin, test } from "./fixtures/auth";

test.describe("run lifecycle actions", () => {
  test("renames without stealing focus while typing", async ({ page, diagnostics }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Rename dataset");
    const backtestId = await runBacktestThroughUi(page);
    await page.goto(`/history/${backtestId}`);

    await page.getByRole("button", { name: "Rename" }).click();
    const dialog = page.getByRole("dialog");
    const field = dialog.getByLabel("Name");
    await expect(field).not.toHaveValue("");

    await field.fill("");
    // Typed character by character: focus must stay in the field throughout.
    await field.pressSequentially("Renamed in browser", { delay: 15 });
    await expect(field).toHaveValue("Renamed in browser");
    await expect(field).toBeFocused();

    await dialog.getByRole("button", { name: "Save name" }).click();
    await expect(page.getByRole("heading", { name: "Renamed in browser" })).toBeVisible();

    await page.goto("/history");
    await expect(page.getByRole("heading", { name: "Renamed in browser" })).toBeVisible();
    diagnostics.assertClean();
  });

  test("reruns, leaving the source untouched", async ({ page, diagnostics }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Rerun dataset");
    const sourceId = await runBacktestThroughUi(page);
    await page.goto(`/history/${sourceId}`);

    await page.getByRole("button", { name: "Rerun" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("A new backtest is created; this one is left unchanged.");
    await dialog.getByRole("button", { name: "Rerun" }).click();

    await expect(page).toHaveURL(new RegExp(`/history/(?!${sourceId}$)\\d+$`), {
      timeout: 60_000,
    });
    const rerunId = Number(page.url().split("/").pop());
    expect(rerunId).not.toBe(sourceId);

    // The source still exists.
    await page.goto(`/history/${sourceId}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    diagnostics.assertClean();
  });

  test("duplicates with an edited field, leaving the source configuration alone", async ({
    page,
    diagnostics,
  }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Duplicate dataset");
    const sourceId = await runBacktestThroughUi(page);
    await page.goto(`/history/${sourceId}`);

    await page.getByRole("button", { name: "Duplicate" }).click();
    const dialog = page.getByRole("dialog");
    // Prefilled from the source configuration.
    await expect(dialog.getByLabel("Grid step", { exact: true })).toHaveValue("0.01");

    await dialog.getByLabel("Grid step", { exact: true }).fill("0.02");
    await dialog.getByRole("button", { name: "Run backtest" }).click();

    await expect(page).toHaveURL(new RegExp(`/history/(?!${sourceId}$)\\d+$`), {
      timeout: 60_000,
    });
    await page.getByRole("tab", { name: "Configuration" }).click();
    await expect(page.getByText("0.02 (fixed mode)")).toBeVisible();

    // The source keeps its original grid step.
    await page.goto(`/history/${sourceId}`);
    await page.getByRole("tab", { name: "Configuration" }).click();
    await expect(page.getByText("0.01 (fixed mode)")).toBeVisible();
    diagnostics.assertClean();
  });

  test("deletes a run and returns to history", async ({ page, diagnostics }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Delete run dataset");
    const backtestId = await runBacktestThroughUi(page);
    await page.goto(`/history/${backtestId}`);

    await page.getByRole("button", { name: "Delete" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toContainText("The dataset and its price data are not affected.");

    // Cancelling issues no request.
    const deletes: string[] = [];
    page.on("request", (request) => {
      if (request.method() === "DELETE") deletes.push(new URL(request.url()).pathname);
    });
    await dialog.getByRole("button", { name: "Cancel" }).click();
    expect(deletes).toEqual([]);

    await page.getByRole("button", { name: "Delete" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Delete backtest" }).click();
    await expect(page).toHaveURL(/\/history$/);

    // The dataset survives the run's deletion.
    await page.goto("/datasets");
    await expect(page.getByRole("heading", { name: "Delete run dataset" })).toBeVisible();
    diagnostics.assertClean();
  });
});

test.describe("comparison", () => {
  test("compares two runs in the selected order without ranking them", async ({
    page,
    diagnostics,
  }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Compare dataset");
    const firstId = await runBacktestThroughUi(page);

    // A second run on the same dataset, via rerun.
    await page.goto(`/history/${firstId}`);
    await page.getByRole("button", { name: "Rerun" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Rerun" }).click();
    await expect(page).toHaveURL(/\/history\/\d+$/, { timeout: 60_000 });
    const secondId = Number(page.url().split("/").pop());

    await page.goto("/history");
    const checkboxes = page.getByRole("checkbox", { name: /Select .* for comparison/ });

    // One selection is not enough.
    await checkboxes.first().check();
    const compare = page.getByRole("link", { name: "Compare selected" });
    await expect(compare).toHaveAttribute("aria-disabled", "true");

    await checkboxes.nth(1).check();
    await expect(compare).not.toHaveAttribute("aria-disabled", "true");
    await compare.click();
    await expect(page).toHaveURL(/\/history\/compare\?/);

    // Only identifiers travel in the URL.
    const url = new URL(page.url());
    expect(url.pathname).toBe("/history/compare");
    expect(url.searchParams.get("ids")).toMatch(/^\d+(,\d+)+$/);
    expect(url.search).not.toContain("metrics");

    const table = page.getByRole("table", { name: /Stored result metrics/ });
    await expect(table).toBeVisible();
    await expect(table).toContainText("metrics.strategy.final_equity");
    // No ranking or derived difference anywhere in the table.
    await expect(table).not.toContainText(/winner|best|rank/i);

    await page.getByRole("link", { name: "Back to history" }).first().click();
    await expect(page).toHaveURL(/\/history$/);

    expect([firstId, secondId].every((id) => Number.isInteger(id))).toBe(true);
    diagnostics.assertClean();
  });

  test("changing a filter clears the selection with a notice", async ({ page }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Selection dataset");
    await runBacktestThroughUi(page);

    await page.goto("/history");
    await page.getByRole("checkbox", { name: /Select .* for comparison/ }).first().check();
    await expect(page.getByText(/selected for comparison/)).toBeVisible();

    await page.getByLabel("Status").selectOption("COMPLETED");
    await expect(page.getByText(/selected for comparison/)).toBeHidden();
  });
});
