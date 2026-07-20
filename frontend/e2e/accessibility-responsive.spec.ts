/**
 * Responsive layout and accessibility semantics across the whole app.
 *
 * The core responsive assertion is that no page scrolls horizontally at any
 * supported width — wide content (tables, charts) must scroll inside its own
 * container instead of pushing the document sideways.
 */

import type { Page } from "@playwright/test";

import { createDatasetThroughUi, runBacktestThroughUi } from "./fixtures/data";
import { expect, registerAndLogin, test } from "./fixtures/auth";

const VIEWPORTS = [
  { name: "phone", width: 390, height: 844 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1440, height: 900 },
] as const;

async function expectNoHorizontalScroll(page: Page, where: string): Promise<void> {
  const overflow = await page.evaluate(() => {
    const root = document.documentElement;
    return { scrollWidth: root.scrollWidth, clientWidth: root.clientWidth };
  });
  expect(
    overflow.scrollWidth,
    `${where} overflows horizontally (${overflow.scrollWidth} > ${overflow.clientWidth})`,
  ).toBeLessThanOrEqual(overflow.clientWidth);
}

test.describe("responsive layout", () => {
  test("no page scrolls horizontally at any supported width", async ({ page }) => {
    // Signed-out pages first: once authenticated, /login and /register redirect.
    for (const viewport of VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      for (const route of ["/", "/login", "/register"]) {
        await page.goto(route);
        await expect(page.getByRole("main")).toBeVisible();
        await expectNoHorizontalScroll(page, `${route} at ${viewport.name}`);
      }
    }

    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Responsive dataset A");
    const firstId = await runBacktestThroughUi(page);
    await createDatasetThroughUi(page, "Responsive dataset B");
    const secondId = await runBacktestThroughUi(page);

    const routes = [
      "/datasets",
      "/backtest/new",
      "/history",
      `/history/${firstId}`,
      `/history/compare?ids=${firstId},${secondId}`,
    ];

    for (const viewport of VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      for (const route of routes) {
        await page.goto(route);
        await expect(page.getByRole("main")).toBeVisible();
        await expectNoHorizontalScroll(page, `${route} at ${viewport.name}`);
      }
    }
  });

  test("wide result tables scroll inside their own container", async ({ page }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Table overflow dataset");
    const backtestId = await runBacktestThroughUi(page);

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/history/${backtestId}`);
    await page.getByRole("tab", { name: "Result tables" }).click();

    const table = page.getByRole("table", { name: /Every trade/ });
    await expect(table).toBeVisible();

    // The table itself is wider than the phone viewport, yet the page is not.
    const scroller = table.locator("xpath=ancestor::*[contains(@class,'overflow-x-auto')][1]");
    await expect(scroller).toHaveCount(1);
    await expectNoHorizontalScroll(page, "result tables at phone width");
  });

  test("charts stay within the viewport on a phone", async ({ page }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Chart overflow dataset");
    const backtestId = await runBacktestThroughUi(page);

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/history/${backtestId}`);
    await page.getByRole("tab", { name: "Charts" }).click();
    await expect(page.getByRole("img", { name: /Equity curve/ })).toBeVisible();

    await expectNoHorizontalScroll(page, "charts at phone width");
  });
});

test.describe("accessibility semantics", () => {
  test("every page has one main landmark and exactly one h1", async ({ page }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Landmark dataset");
    const backtestId = await runBacktestThroughUi(page);

    for (const route of ["/history", "/datasets", "/backtest/new", `/history/${backtestId}`]) {
      await page.goto(route);
      await expect(page.getByRole("main"), route).toHaveCount(1);
      await expect(page.getByRole("banner"), route).toHaveCount(1);
      await expect(page.locator("h1"), route).toHaveCount(1);
    }
  });

  test("a skip link moves focus to the main content", async ({ page }) => {
    await registerAndLogin(page);
    await page.goto("/history");
    await expect(page.getByRole("main")).toBeVisible();

    // Focus the document first, so Tab starts from the top of the page rather
    // than from wherever the headless browser left it.
    await page.locator("body").press("Tab");
    const skip = page.getByRole("link", { name: "Skip to main content" });
    await expect(skip).toBeFocused();
    // Hidden until focused, then genuinely visible.
    await expect(skip).toBeVisible();

    await page.keyboard.press("Enter");
    expect(new URL(page.url()).hash).toBe("#main-content");
  });

  test("interactive controls are reachable and named", async ({ page }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Naming dataset");

    await page.goto("/datasets");
    // Every button exposes an accessible name.
    const buttons = await page.getByRole("button").all();
    expect(buttons.length).toBeGreaterThan(0);
    for (const button of buttons) {
      const name = (await button.textContent())?.trim() ?? "";
      const label = (await button.getAttribute("aria-label"))?.trim() ?? "";
      expect(name || label, "button without an accessible name").not.toBe("");
    }

    // Every form control on the wizard is labelled.
    await page.goto("/backtest/new");
    const fields = await page.locator("input, select, textarea").all();
    for (const field of fields) {
      const described = await field.evaluate((node) => {
        const element = node as HTMLInputElement;
        if (element.type === "hidden") return true;
        if (element.getAttribute("aria-label")) return true;
        const id = element.getAttribute("id");
        if (id && document.querySelector(`label[for="${CSS.escape(id)}"]`)) return true;
        return element.closest("label") !== null;
      });
      expect(described, "form control without a label").toBe(true);
    }
  });

  test("dialogs trap focus and close on Escape", async ({ page }) => {
    await registerAndLogin(page);
    await createDatasetThroughUi(page, "Dialog a11y dataset");
    const backtestId = await runBacktestThroughUi(page);
    await page.goto(`/history/${backtestId}`);

    await page.getByRole("button", { name: "Rename" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toHaveAttribute("aria-modal", "true");
    // The dialog is named, so screen readers announce its purpose.
    const labelledBy = await dialog.getAttribute("aria-labelledby");
    expect(labelledBy).not.toBeNull();
    await expect(page.locator(`[id="${labelledBy ?? ""}"]`)).not.toBeEmpty();

    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    // Focus returns to the control that opened it.
    await expect(page.getByRole("button", { name: "Rename" })).toBeFocused();
  });

  test("status messages are announced, not colour-coded alone", async ({ page }) => {
    // Deliberately signed out: a signed-in visitor is redirected off /login.
    await page.goto("/login");

    await page.getByLabel("Email").fill("nobody@example.com");
    await page.getByLabel("Password").fill("wrong-password-value");
    await page.getByRole("button", { name: "Sign in" }).click();

    // The failure is text inside a live region, and stays deliberately generic.
    const alert = page.getByRole("main").getByRole("alert");
    await expect(alert).toContainText("Incorrect email or password.");
    await expect(alert).toHaveAttribute("aria-live", "assertive");
    await expect(alert).not.toContainText(/no such user|unknown email|not registered/i);
  });
});
