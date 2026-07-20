import { expect, makeCredentials, registerAndLogin, test } from "./fixtures/auth";

test.describe("authentication", () => {
  test("public landing loads without a session", async ({ page, diagnostics }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Grid Backtester" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Log in" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Register" })).toBeVisible();
    diagnostics.assertClean();
  });

  test("registration does not sign the user in, but login does", async ({
    page,
    diagnostics,
  }) => {
    const credentials = makeCredentials("flow");

    await page.goto("/register");
    await page.getByLabel("Email").fill(credentials.email);
    await page.getByLabel("Password", { exact: true }).fill(credentials.password);
    await page.getByLabel("Confirm password").fill(credentials.password);
    await page.getByRole("button", { name: "Create account" }).click();

    await expect(page.getByText("Account created")).toBeVisible();
    // Still signed out: the protected landing must bounce to login.
    await page.goto("/history");
    await expect(page).toHaveURL(/\/login\?next=%2Fhistory$/);

    await page.getByLabel("Email").fill(credentials.email);
    await page.getByLabel("Password").fill(credentials.password);
    await page.getByRole("button", { name: "Sign in" }).click();

    // ?next= returns the user to the page they asked for.
    await expect(page).toHaveURL(/\/history$/);
    await expect(page.getByText(credentials.email)).toBeVisible();
    diagnostics.assertClean();
  });

  test("the session token is never reachable from JavaScript", async ({ page }) => {
    await registerAndLogin(page);

    const exposure = await page.evaluate(() => ({
      cookie: document.cookie,
      local: Object.keys(window.localStorage),
      session: Object.keys(window.sessionStorage),
    }));

    // HttpOnly means document.cookie cannot see the access token at all.
    expect(exposure.cookie).not.toContain("access_token");
    expect(exposure.local).toEqual([]);
    expect(exposure.session).toEqual([]);

    // Nor is it rendered into the document.
    const html = await page.content();
    expect(html).not.toContain("access_token");
    expect(html).not.toMatch(/eyJ[A-Za-z0-9_-]{10,}/);
  });

  test("signed-in visitors are moved off the auth pages", async ({ page, diagnostics }) => {
    await registerAndLogin(page);

    await page.goto("/login");
    await expect(page).toHaveURL(/\/history$/);

    await page.goto("/register");
    await expect(page).toHaveURL(/\/history$/);

    // The legacy workspace path still resolves to the real landing.
    await page.goto("/app");
    await expect(page).toHaveURL(/\/history$/);
    diagnostics.assertClean();
  });

  test("an off-site next target is refused", async ({ page }) => {
    const credentials = makeCredentials("nextguard");
    await registerAndLogin(page, credentials);
    await page.getByRole("button", { name: "Sign out" }).click();
    // Signing out on /history leaves the guard to re-protect the route, so the
    // page the user was on is preserved as the return target.
    await expect(page).toHaveURL(/\/login\?next=%2Fhistory$/);

    await page.goto("/login?next=https%3A%2F%2Fevil.example");
    await page.getByLabel("Email").fill(credentials.email);
    await page.getByLabel("Password").fill(credentials.password);
    await page.getByRole("button", { name: "Sign in" }).click();

    // Falls back to the safe default rather than leaving the origin.
    await expect(page).toHaveURL(/127\.0\.0\.1:\d+\/history$/);
  });

  test("logout ends the session and re-protects private routes", async ({
    page,
    diagnostics,
  }) => {
    await registerAndLogin(page);
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login\?next=%2Fhistory$/);

    await page.goto("/datasets");
    await expect(page).toHaveURL(/\/login\?next=%2Fdatasets$/);
    diagnostics.assertClean();
  });

  test("wrong credentials show one generic message", async ({ page }) => {
    const credentials = makeCredentials("wrongpw");
    await registerAndLogin(page, credentials);
    await page.getByRole("button", { name: "Sign out" }).click();
    // Let the sign-out redirect settle before submitting, so the POST is not
    // torn down mid-flight by the navigation.
    await expect(page).toHaveURL(/\/login\?next=%2Fhistory$/);

    await page.getByLabel("Email").fill(credentials.email);
    await page.getByLabel("Password").fill("definitely-not-the-password");
    await page.getByRole("button", { name: "Sign in" }).click();

    // Scoped to the form: Next.js also renders a route announcer with role=alert.
    const alert = page.getByRole("main").getByRole("alert");
    await expect(alert).toContainText("Incorrect email or password.");
    // Never discloses which credential was wrong.
    await expect(alert).not.toContainText(/unknown|not found|no account/i);
  });
});
