import { createDatasetThroughUi, runBacktestThroughUi } from "./fixtures/data";
import { expect, registerAndLogin, test } from "./fixtures/auth";

test.describe("history and result dashboard", () => {
  test("lists, filters, and opens a run", async ({ page, diagnostics }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "History dataset");
    const backtestId = await runBacktestThroughUi(page);

    await page.goto("/history");
    await expect(page.getByRole("heading", { name: "Backtest history" })).toBeVisible();
    const card = page.getByRole("listitem").filter({ hasText: "History dataset" });
    await expect(card).toBeVisible();

    // Search narrows the list through the backend.
    await page.getByLabel("Search by name").fill("no-such-backtest-name");
    const emptyState = page.getByText("No backtests match these filters");
    await expect(emptyState).toBeVisible();
    // The empty state's own button, not the filter bar's identically named one.
    await page.getByRole("button", { name: "Clear filters" }).last().click();
    await expect(emptyState).toBeHidden();
    await expect(page.getByRole("listitem").first()).toBeVisible();

    // Status filter round-trips through the URL.
    await page.getByLabel("Status").selectOption("COMPLETED");
    await expect(page).toHaveURL(/status=COMPLETED/);
    await expect(page.getByRole("listitem").first()).toBeVisible();

    // Dataset filter.
    // Exact: run cards carry aria-labels that contain the dataset's name too.
    await page
      .getByLabel("Dataset", { exact: true })
      .selectOption({ label: "History dataset" });
    await expect(page).toHaveURL(/dataset_id=\d+/);
    await expect(page.getByRole("listitem").first()).toBeVisible();

    await page.goto(`/history/${backtestId}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    diagnostics.assertClean();
  });

  test("renders metrics, configuration, charts, and tables", async ({
    page,
    diagnostics,
  }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Dashboard dataset");
    const backtestId = await runBacktestThroughUi(page);

    // Watch for anything the dashboard must never request.
    const forbidden: string[] = [];
    page.on("request", (request) => {
      const path = new URL(request.url()).pathname;
      if (path.includes("price_bars")) forbidden.push(path);
      if (path.includes("/exports/")) forbidden.push(path);
    });

    await page.goto(`/history/${backtestId}`);

    // Overview
    await expect(page.getByRole("heading", { name: "Headline figures" })).toBeVisible();
    // "Final equity" also labels a row in the full strategy metrics section,
    // so this is scoped to the headline block.
    const headline = page.getByRole("region", { name: "Headline figures" });
    await expect(headline.getByText("Final equity")).toBeVisible();

    // Charts tab, including SVG and accessible naming.
    await page.getByRole("tab", { name: "Charts" }).click();
    const equityChart = page.getByRole("img", { name: /Equity curve/ });
    await expect(equityChart).toBeVisible();
    await expect(equityChart.locator("title")).toHaveText(/Equity curve/);
    await expect(equityChart.locator("desc")).not.toBeEmpty();
    await expect(page.getByRole("img", { name: /Drawdown/ })).toBeVisible();
    await expect(page.getByRole("img", { name: /Price with baseline/ })).toBeVisible();

    // Configuration tab shows exact stored values.
    await page.getByRole("tab", { name: "Configuration" }).click();
    await expect(page.getByRole("heading", { name: "Portfolio" })).toBeVisible();
    await expect(page.getByText("0.05 (fixed mode)")).toBeVisible();

    // Result tables.
    await page.getByRole("tab", { name: "Result tables" }).click();
    await expect(page.getByRole("table", { name: /Every trade/ })).toBeVisible();
    await expect(page.getByRole("table", { name: /One row per trading day/ })).toBeVisible();

    // Charts and tabs triggered no API traffic of their own.
    expect(forbidden).toEqual([]);
    diagnostics.assertClean();
  });

  test("tabs are operable by keyboard", async ({ page }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Keyboard dataset");
    const backtestId = await runBacktestThroughUi(page);
    await page.goto(`/history/${backtestId}`);

    const overview = page.getByRole("tab", { name: "Overview" });
    await overview.focus();
    await expect(overview).toHaveAttribute("aria-selected", "true");

    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("tab", { name: "Charts" })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    await page.keyboard.press("End");
    await expect(page.getByRole("tab", { name: "Result tables" })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    await page.keyboard.press("Home");
    await expect(overview).toHaveAttribute("aria-selected", "true");
  });

  test("the dashboard makes exactly one detail request with all includes", async ({
    page,
  }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Request discipline dataset");
    const backtestId = await runBacktestThroughUi(page);

    const detailRequests: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.pathname === `/api/backtests/${backtestId}`) detailRequests.push(url.search);
    });

    await page.goto(`/history/${backtestId}`);
    await expect(page.getByRole("heading", { name: "Headline figures" })).toBeVisible();

    expect(detailRequests).toHaveLength(1);
    expect(detailRequests[0]).toContain(
      "include=trades%2Czone_events%2Cdaily_equity%2Cevent_equity",
    );
  });

  test("history makes one list request, not one per row", async ({ page }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "List discipline dataset");
    await runBacktestThroughUi(page);

    const listRequests: string[] = [];
    const detailRequests: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.pathname === "/api/backtests") listRequests.push(url.search);
      if (/^\/api\/backtests\/\d+$/.test(url.pathname)) detailRequests.push(url.pathname);
    });

    await page.goto("/history");
    await expect(page.getByRole("listitem").first()).toBeVisible();

    expect(listRequests).toHaveLength(1);
    expect(detailRequests).toEqual([]);
  });

  test("a missing run shows the ownership-safe message", async ({ page }) => {
    await registerAndLogin(page);
    await page.goto("/history/999999");

    await expect(page.getByText("Backtest unavailable")).toBeVisible();
    await expect(page.getByText("Backtest not found.")).toBeVisible();
    // Nothing hints at whether the run exists for someone else.
    await expect(page.locator("body")).not.toContainText(/another user|belongs to/i);
    // And no download is offered for a run that did not load.
    await expect(page.getByRole("link", { name: /^Download/ })).toHaveCount(0);
  });
});
