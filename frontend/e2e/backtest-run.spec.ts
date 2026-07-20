import { createDatasetThroughUi } from "./fixtures/data";
import { expect, registerAndLogin, test } from "./fixtures/auth";

test.describe("strategy configuration and execution", () => {
  test("configures, validates, runs, and restores a backtest", async ({
    page,
    diagnostics,
  }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Run dataset");

    await page.getByRole("button", { name: "Configure strategy" }).click();

    // Every field group renders.
    for (const section of [
      "Portfolio",
      "Grid geometry",
      "Price execution",
      "Fees",
      "Slippage",
      "Risk assumptions",
    ]) {
      await expect(page.getByRole("heading", { name: section })).toBeVisible();
    }
    await expect(page.getByRole("heading", { name: "Review before running" })).toBeVisible();

    // A client validation error blocks submission, then is corrected.
    await page.getByLabel("Initial cash").fill("1e5");
    await page.getByRole("button", { name: "Run backtest" }).click();
    await expect(page.getByText(/Enter a plain decimal number/).first()).toBeVisible();
    await expect(page).not.toHaveURL(/backtest_id/);
    await page.getByLabel("Initial cash").fill("10000");

    await page.getByLabel("Initial shares").fill("1000");
    await page.getByLabel("A distance mode").selectOption("FIXED");
    await page.getByLabel("A distance", { exact: true }).fill("0.05");
    await page.getByLabel("C distance mode").selectOption("FIXED");
    await page.getByLabel("C distance", { exact: true }).fill("0.10");
    await page.getByLabel("Grid step mode").selectOption("FIXED");
    await page.getByLabel("Grid step", { exact: true }).fill("0.01");

    const run = page.getByRole("button", { name: "Run backtest" });
    await run.click();
    // RUNNING is a real, textual state while the request is in flight.
    await expect(page.getByText("Running backtest…")).toBeVisible();
    await expect(page.getByLabel("Initial cash")).toBeHidden();

    await expect(page.getByText("Backtest completed")).toBeVisible({ timeout: 60_000 });
    await expect(page).toHaveURL(/backtest_id=\d+/);

    const url = new URL(page.url());
    const backtestId = url.searchParams.get("backtest_id");
    expect(backtestId).toMatch(/^\d+$/);
    // Neither configuration nor metrics travel in the URL.
    expect(url.search).not.toContain("configuration");
    expect(url.search).not.toContain("initial_cash");
    expect(url.search).not.toContain("final_equity");

    // Reloading restores the saved run without re-executing it.
    const runRequests: string[] = [];
    page.on("request", (request) => {
      if (request.method() === "POST" && new URL(request.url()).pathname === "/api/backtests") {
        runRequests.push(request.url());
      }
    });
    await page.reload();
    await expect(page.getByText("Backtest completed")).toBeVisible();
    expect(runRequests).toEqual([]);

    diagnostics.assertClean();
  });

  test("blocks a duplicate run submission", async ({ page }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Double click dataset");
    await page.getByRole("button", { name: "Configure strategy" }).click();

    await page.getByLabel("A distance mode").selectOption("FIXED");
    await page.getByLabel("A distance", { exact: true }).fill("0.05");
    await page.getByLabel("C distance mode").selectOption("FIXED");
    await page.getByLabel("C distance", { exact: true }).fill("0.10");
    await page.getByLabel("Grid step mode").selectOption("FIXED");
    await page.getByLabel("Grid step", { exact: true }).fill("0.01");

    const posts: string[] = [];
    page.on("request", (request) => {
      if (request.method() === "POST" && new URL(request.url()).pathname === "/api/backtests") {
        posts.push(request.url());
      }
    });

    const run = page.getByRole("button", { name: "Run backtest" });
    await run.click();
    // The form is replaced by the running state, so a second click is impossible.
    await expect(page.getByText("Running backtest…")).toBeVisible();
    await expect(page.getByText("Backtest completed")).toBeVisible({ timeout: 60_000 });
    expect(posts).toHaveLength(1);
  });

  test("a configuration the engine rejects keeps the form and its values", async ({
    page,
  }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Rejected dataset");
    await page.getByRole("button", { name: "Configure strategy" }).click();

    // An extremely fine grid over a wide zone is refused by the engine's
    // density cap — a deterministic 422 that creates no run.
    await page.getByLabel("Initial cash").fill("50000");
    await page.getByLabel("A distance mode").selectOption("FIXED");
    await page.getByLabel("A distance", { exact: true }).fill("5");
    await page.getByLabel("C distance mode").selectOption("FIXED");
    await page.getByLabel("C distance", { exact: true }).fill("9");
    await page.getByLabel("Grid step mode").selectOption("FIXED");
    await page.getByLabel("Grid step", { exact: true }).fill("0.0001");

    await page.getByRole("button", { name: "Run backtest" }).click();

    await expect(page.getByText("The backtest could not be started")).toBeVisible({
      timeout: 60_000,
    });
    // Still on the form, with the entered values intact and no run created.
    await expect(page.getByLabel("Initial cash")).toHaveValue("50000");
    expect(new URL(page.url()).searchParams.get("backtest_id")).toBeNull();
  });
});
